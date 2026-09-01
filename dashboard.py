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
    "Blau Farmacêutica (BLAU3)": "BLAU3.SA",
    "Pague Menos (PGMN3)": "PGMN3.SA",
    "RaiaDrogasil (RADL3)": "RADL3.SA",
}

# ==========================================
# HELPERS
# ==========================================
def buscar_linha(df, nomes_possiveis):
    """Procura uma linha (métrica) num DataFrame de demonstrativos do yfinance
    testando múltiplos nomes possíveis, já que a nomenclatura muda entre versões
    da biblioteca. Retorna a Series (indexada pelas datas) ou None."""
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
    """Busca DRE, Balanço Patrimonial e Fluxo de Caixa (anual e trimestral) reais via yfinance."""
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
    """Tenta buscar pontuação ESG real via yfinance. Cobertura para tickers
    brasileiros costuma ser limitada — pode retornar vazio."""
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
    """Consulta em tempo real a API pública da B3 (mesmo endpoint usado para IBOV,
    IBRX etc.) para obter a carteira teórica vigente de um índice (ex.: ISEE = ISE B3,
    ICO2 = Índice Carbono Eficiente B3). Retorna um DataFrame com a composição real
    e atual, publicada pela própria B3 — não é uma estimativa."""
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
    """Verifica se o ticker (ex.: HYPE3) aparece na carteira do índice retornada
    por carregar_composicao_indice_b3. Procura em colunas comuns de código do ativo."""
    if df_indice is None or df_indice.empty:
        return None  # indisponível, não sabemos
    for col in ["cod", "codigo", "asset", "cdAtual", "code"]:
        if col in df_indice.columns:
            valores = df_indice[col].astype(str).str.upper()
            return valores.str.startswith(ticker_base.upper()).any()
    return None


@st.cache_data(ttl=86400)
def carregar_status_pacto_global(participant_id="142300"):
    """Verifica ao vivo, na página pública do UN Global Compact, o status de adesão
    da Hypera S.A. (Pacto Global da ONU) — participante nº 142300, confirmado via
    busca manual em 31/08/2026. ATENÇÃO: faz parsing de texto de uma página HTML
    pública (não há API oficial), então é frágil a mudanças de layout do site —
    validar ao rodar localmente e ajustar os padrões de busca se necessário."""
    import re
    url = f"https://unglobalcompact.org/what-is-gc/participants/{participant_id}"
    try:
        response = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        if response.status_code != 200:
            return {}
        texto = re.sub(r"<[^>]+>", " ", response.text)
        texto = re.sub(r"\s+", " ", texto)

        def extrair(rotulo, parar_em):
            padrao = re.escape(rotulo) + r"\s*:?\s*(.+?)\s*" + parar_em
            m = re.search(padrao, texto)
            return m.group(1).strip() if m else None

        return {
            "status": extrair("Global Compact Status", r"Participant Since"),
            "desde": extrair("Participant Since", r"(Letter of Commitment|Next Communication)"),
            "proxima_cop": extrair(r"due on", r"(Affiliated|Help us)"),
        }
    except Exception:
        return {}


# Conteúdo curado e citado sobre atuação por ODS — NÃO é dado ao vivo (iniciativas específicas
# mudam por relatório anual, não em tempo real). Verificado manualmente via busca em 31/08/2026.
# Fontes: hypera.com.br/sustentabilidade, hypera.com.br/responsabilidade-social,
# unglobalcompact.org/what-is-gc/participants/142300, doisamaisfarma.com.br (S&P Global Sustainability
# Yearbook 2024), ri.hypera.com.br/en/hypera-pharma/esg_integrity.
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
        "Evidência Real e Citada": "Programas declarados de 'segurança hídrica' e redução de consumo de água nas subsidiárias (hypera.com.br/sustentabilidade).",
    },
    {
        "ODS": "ODS 12 — Consumo e Produção Responsáveis",
        "Evidência Real e Citada": "Logística reversa de embalagens e reciclagem de resíduos; Mantecorp Skincare/Inspire360 compensam 100% do GEE das entregas de e-commerce.",
    },
    {
        "ODS": "ODS 13 — Ação Contra a Mudança Climática",
        "Evidência Real e Citada": "Integra o ICO2 B3 (checado ao vivo acima); duas subestações de energia limpa em Anápolis (GO, 2023); redução declarada de emissões de GEE.",
    },
    {
        "ODS": "ODS 15 — Vida Terrestre",
        "Evidência Real e Citada": "Investimento em recuperação de áreas degradadas da bacia hidrográfica do Rio Araguaia (GO) — citado no S&P Global Sustainability Yearbook 2024.",
    },
    {
        "ODS": "ODS 17 — Parcerias e Meios de Implementação",
        "Evidência Real e Citada": "Signatária do Pacto Global da ONU desde 12/2020 (checado ao vivo acima); parcerias com ONGs (Sementes do Amanhã, Instituto Horas da Vida).",
    },
]


@st.cache_data(ttl=86400)
def carregar_demonstrativos_cvm_real(ano, tipo="DRE"):
    """Baixa e processa dados reais de ITR (Demonstrações Financeiras Trimestrais)
    do portal de dados abertos da CVM em tempo real. tipo pode ser DRE, BPA, BPP ou DFC."""
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
    """Busca comunicados e fatos relevantes reais protocolados na CVM (dataset IPE,
    dados abertos). Confirmado via busca: o arquivo é um ZIP, não um CSV solto, em
    https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/IPE/DADOS/ipe_cia_aberta_{ano}.zip
    contendo ipe_cia_aberta_{ano}.csv (encoding windows-1252, separador ';')."""
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

        # A coluna do código CVM pode vir com nomes diferentes conforme a versão do arquivo
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
    """Busca notícias reais e em tempo real via Google News RSS (gratuito, sem API key).
    Cobre veículos de imprensa em geral, não apenas comunicados oficiais da CVM —
    útil para tendências de mercado e notícias que podem impactar o ativo."""
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
    """Busca .info de um ticker par (usa o mesmo cache de carregar_info_ticker)."""
    return carregar_info_ticker(ticker)


@st.cache_data(ttl=21600)
def carregar_google_trends_marcas(marcas, timeframe="today 12-m"):
    """Busca o interesse de busca real (Google Trends, Brasil) para uma lista de
    marcas da Hypera, como um proxy real e gratuito de sazonalidade de demanda.
    NÃO é dado de vendas — é volume relativo de pesquisa (0-100) por semana/mês.
    ATENÇÃO: pytrends usa scraping não oficial do Google Trends e pode falhar por
    rate-limit (HTTP 429). Não foi possível testar esta chamada em ambiente sandbox
    (sem acesso à rede trends.google.com) — validar ao rodar localmente."""
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
status_pacto_global = carregar_status_pacto_global()

ano_atual = datetime.now().year
df_cvm_real = carregar_demonstrativos_cvm_real(ano_atual, tipo="DRE")
if df_cvm_real.empty:
    df_cvm_real = carregar_demonstrativos_cvm_real(ano_atual - 1, tipo="DRE")

df_fatos_relevantes = carregar_fatos_relevantes_cvm(ano_atual)
if df_fatos_relevantes.empty:
    df_fatos_relevantes = carregar_fatos_relevantes_cvm(ano_atual - 1)

# Métricas fundamentalistas reais derivadas de .info (podem vir None se indisponíveis)
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
debt_to_equity_real = info_hypera.get("debtToEquity")
total_debt_real = info_hypera.get("totalDebt")
total_cash_real = info_hypera.get("totalCash")
ebitda_real = info_hypera.get("ebitda")

# Séries de demonstrativos reais (mais recentes)
serie_receita = buscar_linha(demonstrativos_yf["income"], ["Total Revenue", "TotalRevenue"])
serie_lucro_liquido = buscar_linha(demonstrativos_yf["income"], ["Net Income", "NetIncome", "Net Income Common Stockholders"])
serie_ebitda = buscar_linha(demonstrativos_yf["income"], ["EBITDA", "Normalized EBITDA"])

serie_fco = buscar_linha(demonstrativos_yf["cashflow"], ["Operating Cash Flow", "Total Cash From Operating Activities"])
serie_fci = buscar_linha(demonstrativos_yf["cashflow"], ["Investing Cash Flow", "Total Cashflows From Investing Activities"])
serie_fcf_financ = buscar_linha(demonstrativos_yf["cashflow"], ["Financing Cash Flow", "Total Cash From Financing Activities"])
serie_capex = buscar_linha(demonstrativos_yf["cashflow"], ["Capital Expenditure", "CapitalExpenditures"])
serie_fcf_livre = buscar_linha(demonstrativos_yf["cashflow"], ["Free Cash Flow"])

serie_divida_total = buscar_linha(demonstrativos_yf["balance"], ["Total Debt", "TotalDebt"])
serie_divida_cp = buscar_linha(demonstrativos_yf["balance"], ["Current Debt", "Short Long Term Debt", "Current Debt And Capital Lease Obligation"])
serie_divida_lp = buscar_linha(demonstrativos_yf["balance"], ["Long Term Debt", "LongTermDebt", "Long Term Debt And Capital Lease Obligation"])
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

st.sidebar.caption(f"Última execução desta sessão: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")

menu_opcao = st.sidebar.radio(
    "Navegação",
    [
        "Noticias",
        "Visao Geral",
        "Mercado",
        "Analise Tecnica",
        "Fundamentos",
        "Portfolio e Sazonalidade",
        "Sustentabilidade & ODS",
        "Resultados",
        "Fluxo de Caixa",
        "Endividamento",
        "Dividendos",
        "Valuation",
        "Comparacao Setorial",
        "Alertas",
        "Hypera AI Analyst",
        "Anomalias",
        "Forecast",
        "Data Pipeline",
        "Metodologia"
    ]
)

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
        st.warning(
            "Não foi possível carregar o feed real de fatos relevantes da CVM neste momento "
            "(fonte instável ou formato do arquivo mudou). Nenhum dado fictício é exibido nesta versão."
        )

    st.markdown("---")
    st.subheader("🌐 Notícias de Mercado em Tempo Real (Google News)")
    st.caption(
        "Fonte gratuita e sem necessidade de chave de API, cobrindo qualquer veículo de imprensa. "
        "Não passa por curadoria — trate como triagem inicial, não como fonte única de decisão."
    )

    termo_busca = st.text_input(
        "Termo de busca (ajuste para focar em tendências específicas de mercado):",
        value="Hypera Pharma HYPE3"
    )

    df_noticias_reais = carregar_noticias_google_news(termo_busca)
    if not df_noticias_reais.empty:
        for _, row in df_noticias_reais.iterrows():
            st.markdown(f"**[{row['Título']}]({row['Link']})**")
            st.caption(f"{row['Fonte']} · {row['Data']}")
            st.markdown("---")
    else:
        st.warning("Não foi possível carregar notícias no momento. Tente novamente em alguns instantes.")

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
            fig_gauge.update_layout(
                title={'text': "P/L Atual (real, ao vivo)", 'x': 0.5, 'xanchor': 'center'},
                template="plotly_dark", height=320, margin=dict(t=50, b=10)
            )
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
            st.warning("Não foi possível conectar à CVM neste momento. Nenhum dado fictício é exibido no lugar.")

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

        # Guarda o IFR mais recente em sessão para reuso real na aba de Alertas
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
    st.title("💰 Indicadores Fundamentalistas — Hypera Pharma (HYPE3)")
    st.markdown("Rentabilidade e margens obtidas em tempo real via Yahoo Finance (.info).")

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
    st.caption("Pares utilizados: " + ", ".join(k for k in TICKERS_PARES if TICKERS_PARES[k] != TICKER_PRINCIPAL))

elif menu_opcao == "Portfolio e Sazonalidade":
    st.title("💊 Portfólio de Produtos & Sazonalidade de Vendas (HYPE3)")
    st.info(
        "Não existe fonte pública gratuita com **vendas reais** por produto/mês da Hypera "
        "(isso é dado pago de painéis como IQVIA/Nielsen). Como proxy real e gratuito, usamos o "
        "**Google Trends**: volume de busca por marca ao longo do ano, que costuma acompanhar a "
        "demanda sazonal real do consumidor."
    )

    marcas_hypera = ["Benegrip", "Doril", "Naldecon", "Vitergan"]

    st.markdown("---")
    st.subheader("📈 Sazonalidade Real (Google Trends) — Interesse de Busca por Marca")

    if not PYTRENDS_DISPONIVEL:
        st.warning(
            "A biblioteca `pytrends` não está instalada. Rode `pip install pytrends` no ambiente "
            "(ou adicione `pytrends` ao requirements.txt) para habilitar esta seção com dados reais."
        )
    else:
        df_trends = carregar_google_trends_marcas(tuple(marcas_hypera))
        if not df_trends.empty:
            fig_trends = go.Figure()
            cores_trend = ['#00d2ff', '#ff7f0e', '#2ca02c', '#d62728']
            for i, marca in enumerate(marcas_hypera):
                if marca in df_trends.columns:
                    fig_trends.add_trace(go.Scatter(
                        x=df_trends.index, y=df_trends[marca], name=marca,
                        line=dict(color=cores_trend[i % len(cores_trend)])
                    ))
            fig_trends.update_layout(
                template="plotly_dark", height=420,
                yaxis_title="Interesse de Busca (0-100, relativo)",
                xaxis_title="Período (últimos 12 meses)",
                legend=dict(x=0.02, y=0.98)
            )
            st.plotly_chart(fig_trends, use_container_width=True)

            st.markdown("---")
            st.subheader("📋 Mês de Pico de Interesse por Marca (real, calculado)")
            linhas_pico = []
            for marca in marcas_hypera:
                if marca in df_trends.columns and df_trends[marca].max() > 0:
                    data_pico = df_trends[marca].idxmax()
                    linhas_pico.append({
                        "Marca": marca,
                        "Mês de Pico de Busca": data_pico.strftime("%B/%Y"),
                        "Interesse no Pico (0-100)": int(df_trends[marca].max())
                    })
            if linhas_pico:
                st.dataframe(pd.DataFrame(linhas_pico), use_container_width=True, hide_index=True)
        else:
            st.warning(
                "Não foi possível obter dados do Google Trends neste momento (fonte instável, "
                "rate-limit do provedor, ou geografia/termos sem volume suficiente). "
                "Tente novamente em alguns minutos usando 'Atualizar Dados Agora' na barra lateral."
            )

    st.caption(
        "⚠️ Interesse de busca é um proxy de demanda do consumidor, não é volume de vendas real da Hypera. "
        "Use como indicativo direcional de sazonalidade, não como número financeiro."
    )

elif menu_opcao == "Sustentabilidade & ODS":
    st.title("🌱 Sustentabilidade, ESG & ODS — Hypera Pharma")
    st.markdown("Verificação real e ao vivo de participação em índices oficiais de sustentabilidade da B3.")

    st.subheader("📋 Participação em Índices ESG da B3 (verificado ao vivo, API pública B3)")

    def status_indice(pertence):
        if pertence is None:
            return "⚪ Não foi possível verificar agora"
        return "🟢 Sim, está na carteira atual" if pertence else "🔴 Não está na carteira atual"

    col1, col2 = st.columns(2)
    with col1:
        st.metric(label="ISE B3 (Índice de Sustentabilidade Empresarial)", value=status_indice(hypera_no_ise))
    with col2:
        st.metric(label="ICO2 B3 (Índice Carbono Eficiente)", value=status_indice(hypera_no_ico2))

    st.caption(
        "Checagem feita consultando, em tempo real, a carteira teórica vigente publicada pela própria B3 "
        "(mesma API pública usada para IBOV/IBRX). Não é uma estimativa: é a lista oficial do dia."
    )

    st.markdown("---")
    st.subheader("🤝 Adesão ao Pacto Global da ONU (checado ao vivo)")
    if status_pacto_global.get("status"):
        col1, col2, col3 = st.columns(3)
        col1.metric(label="Status", value=status_pacto_global.get("status", "N/D"))
        col2.metric(label="Signatária Desde", value=status_pacto_global.get("desde", "N/D"))
        col3.metric(label="Próxima COP Devida", value=status_pacto_global.get("proxima_cop", "N/D"))
        st.caption("Fonte: unglobalcompact.org/what-is-gc/participants/142300 (perfil público da Hypera S.A.)")
    else:
        st.warning(
            "Não foi possível confirmar o status ao vivo no Pacto Global neste momento. "
            "Verificado manualmente em 31/08/2026: Hypera S.A. é signatária ativa desde 12/2020 "
            "(participante nº 142300)."
        )

    st.markdown("---")
    st.subheader("🎯 Onde a Hypera se Destaca por ODS (conteúdo curado e citado, não é dado ao vivo)")
    st.caption(
        "As linhas abaixo foram levantadas e verificadas manualmente em fontes oficiais (site da Hypera, "
        "perfil no Pacto Global, S&P Global Sustainability Yearbook) — não são atualizadas automaticamente, "
        "já que essas iniciativas são reportadas por ciclo anual, não em tempo real."
    )
    st.dataframe(pd.DataFrame(ODS_DESTAQUE_HYPERA), use_container_width=True, hide_index=True)

    st.markdown("---")
    st.subheader("🌐 Pontuação ESG Detalhada (Yahoo Finance / Sustainalytics)")
    if not df_sustentabilidade_real.empty:
        st.success("Dados de sustentabilidade encontrados via Yahoo Finance para este ativo.")
        st.dataframe(df_sustentabilidade_real, use_container_width=True)
    else:
        st.warning(
            "⚠️ Não há dados ESG detalhados (emissões, pontuação Sustainalytics, etc.) disponíveis via API "
            "pública gratuita para este ativo no momento. Não exibimos números fictícios no lugar."
        )

    st.markdown("---")
    st.subheader("Indicadores de Governança Verificáveis (ao vivo)")
    col1, col2 = st.columns(2)
    with col1:
        st.metric(label="Segmento de Listagem B3", value=info_hypera.get("exchange", "N/D"))
    with col2:
        st.metric(label="Website Oficial", value=info_hypera.get("website", "N/D"))
    st.caption(
        "Para métricas ESG oficiais e granulares (emissões por escopo, relatórios GRI, TCFD, respostas ao "
        "CDP), consulte diretamente o Relatório de Sustentabilidade publicado pela companhia — não existe "
        "API pública gratuita que exponha esse nível de detalhe."
    )

elif menu_opcao == "Resultados":
    st.title("📑 Demonstrações Financeiras — CVM (Dados Reais)")
    st.markdown("Dados oficiais estruturados da Hypera Pharma (HYPE3), direto do portal de dados abertos da CVM.")

    if not df_cvm_real.empty:
        st.success(f"Sucesso! {len(df_cvm_real)} registros reais carregados da CVM.")
        colunas_disp = [c for c in ["CD_CVM", "DS_CONTA", "VL_CONTA", "DT_REFER", "DT_FIM_EXERC"] if c in df_cvm_real.columns]
        st.dataframe(df_cvm_real[colunas_disp] if colunas_disp else df_cvm_real, use_container_width=True, hide_index=True)

        st.markdown("---")
        st.subheader("📊 Principais Contas (dados reais CVM)")
        if "DS_CONTA" in df_cvm_real.columns and "VL_CONTA" in df_cvm_real.columns:
            df_plot = df_cvm_real[["DS_CONTA", "VL_CONTA"]].drop_duplicates(subset="DS_CONTA").head(10)
            fig_res = go.Figure(data=[go.Bar(x=df_plot['DS_CONTA'], y=df_plot['VL_CONTA'], marker_color='#5bc0de')])
            fig_res.update_layout(template="plotly_dark", height=400, margin=dict(t=20, b=120, l=40, r=20), xaxis_title="", yaxis_title="VL_CONTA (R$)")
            st.plotly_chart(fig_res, use_container_width=True)
    else:
        st.warning("Não foi possível carregar os demonstrativos da CVM neste momento.")

    st.markdown("---")
    st.subheader("📊 Receita e Lucro Líquido (Yahoo Finance, real)")
    if serie_receita is not None or serie_lucro_liquido is not None:
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Receita Líquida (último período)", fmt_moeda_bi(valor_mais_recente(serie_receita)))
        with col2:
            st.metric("Lucro Líquido (último período)", fmt_moeda_bi(valor_mais_recente(serie_lucro_liquido)))
    else:
        st.info("Demonstrativos do Yahoo Finance indisponíveis no momento.")

elif menu_opcao == "Fluxo de Caixa":
    st.title("💵 Demonstração do Fluxo de Caixa (DFC) — HYPE3")
    st.markdown("Dados reais extraídos do demonstrativo de fluxo de caixa via Yahoo Finance.")

    fco = valor_mais_recente(serie_fco)
    fci = valor_mais_recente(serie_fci)
    fcf_financ = valor_mais_recente(serie_fcf_financ)
    fcf_livre = valor_mais_recente(serie_fcf_livre)

    col1, col2, col3 = st.columns(3)
    col1.metric(label="Caixa Operacional (FCO)", value=fmt_moeda_bi(fco))
    col2.metric(label="Caixa de Investimento (FCI)", value=fmt_moeda_mi(fci))
    col3.metric(label="Fluxo de Caixa Livre (FCF)", value=fmt_moeda_bi(fcf_livre))

    st.markdown("---")
    if any(v is not None for v in [fco, fci, fcf_financ]):
        st.subheader("📊 Composição do Fluxo de Caixa (último período reportado, real)")
        componentes = ["FCO (Operacional)", "FCI (Investimento)", "FCF (Financiamento)"]
        valores_dfc = [fco or 0, fci or 0, fcf_financ or 0]
        cores_barras = ['#2ca02c', '#d62728', '#ff7f0e']
        fig_dfc = go.Figure(data=[go.Bar(x=componentes, y=valores_dfc, marker_color=cores_barras)])
        fig_dfc.update_layout(template="plotly_dark", height=400, margin=dict(t=20, b=20, l=40, r=20), yaxis_title="R$", xaxis_title="Componentes")
        st.plotly_chart(fig_dfc, use_container_width=True)

        if not demonstrativos_yf["cashflow"].empty and serie_fco is not None and len(serie_fco) > 1:
            st.subheader("📈 Evolução do FCO por Período (real, últimos exercícios)")
            fig_evol = go.Figure(data=[go.Scatter(
                x=[str(c.date()) if hasattr(c, "date") else str(c) for c in serie_fco.index],
                y=serie_fco.values, mode="lines+markers", line=dict(color="#00d2ff")
            )])
            fig_evol.update_layout(template="plotly_dark", height=350, yaxis_title="FCO (R$)")
            st.plotly_chart(fig_evol, use_container_width=True)
    else:
        st.warning("Não foi possível obter o demonstrativo de fluxo de caixa no momento.")

elif menu_opcao == "Endividamento":
    st.title("🏛️ Análise de Endividamento & Alavancagem — HYPE3")
    st.markdown("Dívida bruta, caixa e alavancagem reais, via Yahoo Finance.")

    caixa_atual = total_cash_real if total_cash_real is not None else valor_mais_recente(serie_caixa)
    divida_atual = total_debt_real if total_debt_real is not None else valor_mais_recente(serie_divida_total)
    divida_liquida = None
    if divida_atual is not None and caixa_atual is not None:
        divida_liquida = divida_atual - caixa_atual

    divida_liquida_ebitda = None
    if divida_liquida is not None and ebitda_real:
        divida_liquida_ebitda = divida_liquida / ebitda_real
    st.session_state['divida_liquida_ebitda'] = divida_liquida_ebitda

    col1, col2, col3, col4 = st.columns(4)
    col1.metric(label="Dívida Bruta", value=fmt_moeda_bi(divida_atual))
    col2.metric(label="Caixa e Equivalentes", value=fmt_moeda_bi(caixa_atual))
    col3.metric(label="Dívida Líquida", value=fmt_moeda_bi(divida_liquida))
    col4.metric(label="Dívida Líq. / EBITDA", value=f"{divida_liquida_ebitda:.2f}x" if divida_liquida_ebitda is not None else "N/D")

    st.markdown("---")
    if serie_divida_total is not None and len(serie_divida_total) > 1:
        st.subheader("📊 Evolução Real da Dívida Bruta por Exercício")
        fig_div = go.Figure(data=[go.Bar(
            x=[str(c.date()) if hasattr(c, "date") else str(c) for c in serie_divida_total.index],
            y=serie_divida_total.values, marker_color='#1f77b4'
        )])
        fig_div.update_layout(template="plotly_dark", height=400, margin=dict(t=20, b=20, l=40, r=20), yaxis_title="R$", xaxis_title="Exercício")
        st.plotly_chart(fig_div, use_container_width=True)
    else:
        st.info("Série histórica de dívida indisponível no momento via Yahoo Finance.")

elif menu_opcao == "Dividendos":
    st.title("💎 Histórico de Dividendos & Proventos — HYPE3")
    st.markdown("Histórico real de pagamentos de dividendos/JCP via Yahoo Finance.")

    col1, col2, col3 = st.columns(4)[:3]
    st.columns_placeholder = None
    colA, colB, colC, colD = st.columns(4)
    colA.metric(label="Dividend Yield (atual)", value=fmt_pct(dividend_yield_real))
    colB.metric(label="Payout Ratio (atual)", value=fmt_pct(payout_real))
    if not df_dividendos_real.empty:
        colC.metric(label="Último Provento", value=f"R$ {df_dividendos_real.iloc[-1]['Valor por Ação (R$)']:.2f}")
        colD.metric(label="Total de Pagamentos (histórico)", value=str(len(df_dividendos_real)))
    else:
        colC.metric(label="Último Provento", value="N/D")
        colD.metric(label="Total de Pagamentos", value="N/D")

    st.markdown("---")
    if not df_dividendos_real.empty:
        st.subheader("📋 Histórico Real de Pagamentos (por data)")
        st.dataframe(df_dividendos_real.sort_values("Data", ascending=False), use_container_width=True, hide_index=True)

        st.markdown("---")
        st.subheader("📊 Total de Proventos por Ano (real, somado a partir dos pagamentos)")
        df_por_ano = df_dividendos_real.groupby("Ano")["Valor por Ação (R$)"].sum().reset_index()
        fig_div_hist = go.Figure(data=[go.Bar(x=df_por_ano['Ano'].astype(str), y=df_por_ano['Valor por Ação (R$)'], marker_color='#2ca02c')])
        fig_div_hist.update_layout(template="plotly_dark", height=400, margin=dict(t=20, b=20, l=40, r=20), yaxis_title="R$ por ação", xaxis_title="Ano")
        st.plotly_chart(fig_div_hist, use_container_width=True)
    else:
        st.warning("Não foi possível obter o histórico real de dividendos no momento.")

elif menu_opcao == "Valuation":
    st.title("🧮 Valuation & Múltiplos — HYPE3")
    st.markdown("Simulação de Fluxo de Caixa Descontado (com parâmetros definidos por você) e múltiplos de mercado atuais e reais.")

    st.subheader("⚙️ Parâmetros do Modelo de Gordon / FCD")
    fco_base_default = fco if 'fco' in dir() and fco else (valor_mais_recente(serie_fco) or 2_000_000_000.0)

    col_v1, col_v2, col_v3 = st.columns(3)
    with col_v1:
        fco_base = st.number_input("Fluxo de Caixa Base (R$)", value=float(fco_base_default), step=100_000_000.0)
    with col_v2:
        wacc_val = st.slider("Taxa de Desconto / WACC (%)", 5.0, 20.0, 11.5, 0.5)
    with col_v3:
        g_val = st.slider("Taxa de Crescimento Perpetuidade (g %)", 0.0, 6.0, 3.0, 0.5)

    if st.button("Processar Cálculo de Valuation"):
        if wacc_val > g_val:
            valor_firma = fco_base / ((wacc_val - g_val) / 100.0)
            st.success(f"Valor Intrínseco Calculado da Firma (Gordon): R$ {valor_firma:,.2f}")
        else:
            st.error("WACC deve ser maior que a taxa de crescimento (g) para o modelo convergir.")

    st.markdown("---")
    st.subheader("📋 Múltiplos Atuais (ao vivo, Yahoo Finance)")

    df_multiplos = pd.DataFrame({
        "Múltiplo": ["P/L", "P/VP", "EV/EBITDA", "Dividend Yield"],
        "Hypera (atual, real)": [
            f"{pe_real:.1f}" if pe_real else "N/D",
            f"{pvp_real:.1f}" if pvp_real else "N/D",
            f"{ev_ebitda_real:.1f}" if ev_ebitda_real else "N/D",
            fmt_pct(dividend_yield_real),
        ],
    })
    st.dataframe(df_multiplos, use_container_width=True, hide_index=True)
    st.caption(
        "Múltiplos históricos (média/mín/máx de 5 anos) exigiriam reconstrução de EPS e VPA por período, "
        "não incluída nesta versão para evitar estimativas não verificadas. Removido em vez de mantido fictício."
    )

elif menu_opcao == "Comparacao Setorial":
    st.title("🏭 Comparação Setorial & Benchmarking — Saúde & Farmacêutico")
    st.markdown("Comparação em tempo real da Hypera Pharma (HYPE3) frente aos pares, via Yahoo Finance.")

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

    st.subheader("📋 Tabela Comparativa de Pares (dados ao vivo)")
    st.dataframe(df_setor_completo, use_container_width=True, hide_index=True)

    st.markdown("---")
    st.subheader("📊 Benchmarking: Margem Líquida vs ROE (real)")
    fig_setor_bench = go.Figure(data=[
        go.Bar(name='Margem Líquida (%)', x=df_setor_completo['Empresa / Ticker'], y=df_setor_completo['Margem Líquida (%)'], marker_color='#1f77b4'),
        go.Bar(name='ROE (%)', x=df_setor_completo['Empresa / Ticker'], y=df_setor_completo['ROE (%)'], marker_color='#2ca02c')
    ])
    fig_setor_bench.update_layout(barmode='group', template="plotly_dark", height=450, margin=dict(t=20, b=40, l=40, r=20), yaxis_title="Percentual (%)", xaxis_title="Empresas", legend=dict(x=0.85, y=0.95))
    st.plotly_chart(fig_setor_bench, use_container_width=True)

elif menu_opcao == "Alertas":
    st.title("🚨 Central de Alertas & Monitoramento de Riscos — HYPE3")
    st.markdown("Regras aplicadas sobre valores reais e calculados nas demais abas.")

    ifr_atual = st.session_state.get('ifr_atual')
    divida_liquida_ebitda_atual = st.session_state.get('divida_liquida_ebitda')

    variacao_receita = None
    if serie_receita is not None and len(serie_receita) > 1:
        atual_r = serie_receita.iloc[0]
        anterior_r = serie_receita.iloc[1]
        if anterior_r:
            variacao_receita = ((atual_r - anterior_r) / abs(anterior_r)) * 100

    linhas_alerta = []

    def status_regra(valor, limite_min=None, limite_max=None):
        if valor is None:
            return "⚪ Sem dado"
        if limite_max is not None and valor > limite_max:
            return "🔴 Atenção"
        if limite_min is not None and valor < limite_min:
            return "🔴 Atenção"
        return "🟢 Normal"

    linhas_alerta.append({
        "Métrica": "Dívida Líquida / EBITDA",
        "Limite": "> 3.00x",
        "Valor Atual (real)": f"{divida_liquida_ebitda_atual:.2f}x" if divida_liquida_ebitda_atual is not None else "N/D (visite a aba Endividamento primeiro)",
        "Status": status_regra(divida_liquida_ebitda_atual, limite_max=3.0)
    })
    linhas_alerta.append({
        "Métrica": "IFR (14) — Sobrecompra/Sobrevenda",
        "Limite": "> 70 ou < 30",
        "Valor Atual (real)": f"{ifr_atual:.1f}" if ifr_atual is not None else "N/D (visite a aba Análise Técnica primeiro)",
        "Status": status_regra(ifr_atual, limite_min=30, limite_max=70)
    })
    linhas_alerta.append({
        "Métrica": "Variação de Receita (período mais recente)",
        "Limite": "< 0% (queda)",
        "Valor Atual (real)": f"{variacao_receita:+.1f}%" if variacao_receita is not None else "N/D",
        "Status": status_regra(variacao_receita, limite_min=0)
    })

    df_alertas = pd.DataFrame(linhas_alerta)
    st.dataframe(df_alertas, use_container_width=True, hide_index=True)
    st.caption(
        "Dica: visite as abas Análise Técnica e Endividamento nesta sessão antes de checar Alertas, "
        "para que os valores calculados fiquem disponíveis aqui (armazenados em st.session_state)."
    )

elif menu_opcao == "Hypera AI Analyst":
    st.title("🧠 Hypera AI Analyst — Assistente Baseado em Regras (dados reais)")
    st.markdown(
        "**Importante:** este assistente não é um modelo de linguagem/IA generativa — é um sistema de "
        "regras por palavra-chave que insere valores reais e ao vivo nas respostas."
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
                "Não foi possível obter todos os dados no momento."
            )

elif menu_opcao == "Anomalias":
    st.title("🔎 Detecção de Anomalias & Outliers — HYPE3")
    st.markdown("Cálculo real de Z-Score sobre os retornos diários de preço (não é mais um texto fixo).")

    if not df_mercado_real.empty:
        retornos = df_mercado_real['Close'].pct_change().dropna()
        media_ret = retornos.mean()
        std_ret = retornos.std()
        z_scores = (retornos - media_ret) / std_ret if std_ret else pd.Series(dtype=float)

        limiar = 2.5
        anomalias_detectadas = z_scores[abs(z_scores) > limiar]

        col1, col2, col3 = st.columns(3)
        col1.metric(label="Anomalias Detectadas (Z-Score, período carregado)", value=str(len(anomalias_detectadas)))
        col2.metric(label="Método", value="Z-Score sobre retornos diários")
        col3.metric(label="Limiar", value=f"|Z| > {limiar}")

        st.markdown("---")
        if not anomalias_detectadas.empty:
            df_anom = df_mercado_real.loc[anomalias_detectadas.index, ["Date", "Close"]].copy()
            df_anom["Retorno Diário (%)"] = (retornos.loc[anomalias_detectadas.index] * 100).round(2)
            df_anom["Z-Score"] = z_scores.loc[anomalias_detectadas.index].round(2)
            st.dataframe(df_anom, use_container_width=True, hide_index=True)
        else:
            st.success("Nenhuma anomalia estatística (|Z| > 2.5) detectada nos retornos diários do período carregado.")
    else:
        st.warning("Sem dados de mercado disponíveis para rodar a detecção de anomalias.")

elif menu_opcao == "Forecast":
    st.title("🔮 Projeções & Forecast Financeiro — HYPE3")
    st.markdown("Regressão linear real sobre a série histórica de Receita e Lucro Líquido (Yahoo Finance).")

    if serie_receita is not None and len(serie_receita) >= 2:
        anos_idx = np.arange(len(serie_receita))[::-1]  # mais antigo = 0
        receita_vals = serie_receita.values[::-1]
        coef_receita = np.polyfit(anos_idx, receita_vals, 1)
        proximo_periodo = len(serie_receita)
        receita_projetada = np.polyval(coef_receita, proximo_periodo)

        lucro_projetado = None
        if serie_lucro_liquido is not None and len(serie_lucro_liquido) >= 2:
            lucro_vals = serie_lucro_liquido.values[::-1]
            coef_lucro = np.polyfit(np.arange(len(lucro_vals)), lucro_vals, 1)
            lucro_projetado = np.polyval(coef_lucro, len(lucro_vals))

        col1, col2, col3 = st.columns(3)
        col1.metric(label="Receita Projetada (Próx. Período)", value=fmt_moeda_bi(receita_projetada))
        col2.metric(label="Lucro Líquido Projetado", value=fmt_moeda_bi(lucro_projetado))
        col3.metric(label="Modelo", value="Regressão Linear (real, numpy.polyfit)")

        st.markdown("---")
        st.subheader("📈 Série Histórica Real + Projeção")
        datas_hist = [str(c.date()) if hasattr(c, "date") else str(c) for c in serie_receita.index][::-1]
        fig_f = go.Figure()
        fig_f.add_trace(go.Scatter(x=datas_hist, y=receita_vals, name="Receita Líquida (real)", line=dict(color="#00d2ff", width=2), mode='lines+markers'))
        fig_f.add_trace(go.Scatter(x=datas_hist + ["Projeção"], y=list(receita_vals) + [receita_projetada], name="Projeção (linear)", line=dict(color="#ff7f0e", width=2, dash="dash"), mode='lines+markers'))
        fig_f.update_layout(template="plotly_dark", height=400, margin=dict(t=20, b=20, l=40, r=20), yaxis_title="R$", xaxis_title="Período")
        st.plotly_chart(fig_f, use_container_width=True)
        st.caption(
            "Projeção baseada em regressão linear simples sobre poucos pontos históricos anuais disponíveis "
            "via Yahoo Finance — trate como indicativo de tendência, não como previsão robusta (não é ARIMA)."
        )
    else:
        st.warning("Histórico insuficiente de receita disponível via Yahoo Finance para gerar uma projeção real.")

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
        st.markdown(f"### {datetime.now().strftime('%H:%M:%S')}")
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
        "💡 Nota Metodológica: seções sem fonte pública gratuita confiável (ESG detalhado, sazonalidade de "
        "portfólio por produto) são claramente identificadas na tela como conteúdo ilustrativo, e não "
        "apresentadas como dado oficial em tempo real."
    )

else:
    st.title(f"{menu_opcao}")
    st.info("Módulo carregado com sucesso.")
