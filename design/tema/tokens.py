"""
Tokens de design do Hidrolog.

Fonte única de verdade para cores, tipografia, espaçamentos, raios e tamanhos.
O QSS (qss.py), o estilo dos gráficos (graficos.py) e todos os componentes
leem daqui: nenhuma tela deve ter cor ou tamanho escrito à mão.

A cor de ação padrão é um azul de "água"; cada instalação pode trocá-la na
pasta de marca (ver marca.py). Os tons de interface foram escurecidos ou
clareados para passar no contraste AA (ver tema/contraste.py e o README).
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Marca (cores exatas da logo; não usar como cor de texto)
# ---------------------------------------------------------------------------
MARCA = {
    "azul": "#56A5CA",      # hidrograma
    "verde": "#579770",     # vegetação
    "terra": "#B77959",     # solo
    "grafite": "#4B4B4D",   # letreiro
    "placa": "#FFFFFF",     # fundo sobre o qual a logo é aplicada
}

# ---------------------------------------------------------------------------
# Cores de interface por tema (nomes semânticos: o papel, não a cor).
# As cores da marca (primaria*, foco, selecao) ficam em CORES_MARCA_PADRAO.
# ---------------------------------------------------------------------------
CORES: dict[str, dict[str, str]] = {
    "claro": {
        # superfícies
        "fundo": "#F3F4F6",               # fundo da área de conteúdo
        "superficie": "#FFFFFF",          # cartões, tabelas, diálogos
        "superficie_alt": "#F7F8F9",      # cabeçalho de tabela, linhas alternadas
        "superficie_lateral": "#FAFAFB",  # barra lateral e cabeçalho
        "superficie_elevada": "#FFFFFF",  # menus, dicas
        "hover": "#EEF0F3",               # fundo de item sob o mouse
        # bordas
        "borda": "#DDE1E6",               # divisórias, contorno de cartões
        "borda_controle": "#8C949E",      # contorno de campos (≥ 3:1)
        "borda_forte": "#6B737D",
        # texto
        "texto": "#1B1F24",
        "texto_secundario": "#4E555E",
        "texto_terciario": "#646B74",     # legendas, unidades (≥ 4,5:1)
        "texto_desabilitado": "#9AA1A9",
        "texto_sobre_primaria": "#FFFFFF",
        # estados
        "sucesso": "#2B7349",
        "sucesso_suave": "#E3F2E8",
        "alerta": "#8A5000",
        "alerta_suave": "#FCF0DA",
        "erro": "#B3261E",
        "erro_hover": "#951F19",
        "erro_suave": "#FBE8E6",
        "info": "#185C80",
        "info_suave": "#E4F0F6",
        "neutro": "#4E555E",
        "neutro_suave": "#ECEEF1",
    },
    "escuro": {
        "fundo": "#121417",
        "superficie": "#1A1D21",
        "superficie_alt": "#1F2328",
        "superficie_lateral": "#16191C",
        "superficie_elevada": "#23272D",
        "hover": "#252A30",
        "borda": "#2C3138",
        "borda_controle": "#6C7580",
        "borda_forte": "#8A929C",
        "texto": "#E7E9EC",
        "texto_secundario": "#B3B9C1",
        "texto_terciario": "#969DA7",
        "texto_desabilitado": "#5E6570",
        "texto_sobre_primaria": "#0B1A22",
        "sucesso": "#6CC08F",
        "sucesso_suave": "#15291E",
        "alerta": "#E6AE5C",
        "alerta_suave": "#2E2412",
        "erro": "#F28B82",
        "erro_hover": "#F5A49D",
        "erro_suave": "#3A1C1A",
        "info": "#86C3E2",
        "info_suave": "#18303D",
        "neutro": "#B3B9C1",
        "neutro_suave": "#262B31",
    },
}

# ---------------------------------------------------------------------------
# Cores da marca na interface (trocáveis: ver tema/marca.py)
# ---------------------------------------------------------------------------
# Só estas chaves mudam numa troca de marca (white label). Superfícies, texto,
# estados (sucesso/alerta/erro/info), status e gráficos ficam como estão.
CHAVES_MARCA = ("primaria", "primaria_hover", "primaria_pressionada", "primaria_suave",
                "primaria_texto", "foco", "selecao")

CORES_MARCA_PADRAO: dict[str, dict[str, str]] = {
    "claro": {  # azul de referência #56A5CA, escurecido para passar no AA
        "primaria": "#1D6A92",
        "primaria_hover": "#17587A",
        "primaria_pressionada": "#124663",
        "primaria_suave": "#E4F0F6",      # item ativo na navegação
        "primaria_texto": "#185C80",      # texto na cor da marca sobre fundos claros
        "foco": "#1D6A92",
        "selecao": "#D3E6F0",
    },
    "escuro": {
        "primaria": "#6DB6DB",
        "primaria_hover": "#8AC5E3",
        "primaria_pressionada": "#A6D4EA",
        "primaria_suave": "#18303D",
        "primaria_texto": "#86C3E2",
        "foco": "#86C3E2",
        "selecao": "#1F3A4A",
    },
}

_cores_marca: dict[str, dict[str, str]] = {m: dict(v) for m, v in CORES_MARCA_PADRAO.items()}


def definir_cores_marca(cores_por_modo: dict[str, dict[str, str]] | None) -> None:
    """Troca as cores da marca (None volta ao padrão). Chamado por tema.marca."""
    global _cores_marca
    base = {m: dict(v) for m, v in CORES_MARCA_PADRAO.items()}
    for modo, valores in (cores_por_modo or {}).items():
        desconhecidas = set(valores) - set(CHAVES_MARCA)
        if desconhecidas:
            raise ValueError(f"chaves que não são da marca: {sorted(desconhecidas)}")
        base[_modo_valido(modo)].update(valores)
    _cores_marca = base


# Tons aceitos por selos, faixas de aviso e cartões de métrica.
TONS = ("neutro", "info", "sucesso", "alerta", "erro")

# ---------------------------------------------------------------------------
# Gráficos
# ---------------------------------------------------------------------------
# Categóricas: azul, terra e verde derivados da logo, mais três tons
# distintos. Azul x laranja vêm primeiro (par seguro para daltonismo).
GRAFICO: dict[str, dict] = {
    "claro": {
        "categoricas": ["#1F6E9C", "#C0652B", "#2E8555", "#7357A6", "#B8433A", "#5B6773"],
        "fundo": "#FFFFFF",
        "fundo_eixos": "#FFFFFF",
        "texto": "#1B1F24",
        "texto_secundario": "#4E555E",
        "eixo": "#8C949E",
        "grade": "#E3E6EA",
        "sombreado_alfa": 0.10,
        "mapa_cores": "viridis",   # sequencial, perceptualmente uniforme
    },
    "escuro": {
        "categoricas": ["#6DB6DB", "#E8955C", "#6CC08F", "#B39DDB", "#EF7B70", "#A3ADB8"],
        "fundo": "#1A1D21",
        "fundo_eixos": "#1A1D21",
        "texto": "#E7E9EC",
        "texto_secundario": "#B3B9C1",
        "eixo": "#6C7580",
        "grade": "#2C3138",
        "sombreado_alfa": 0.14,
        "mapa_cores": "viridis",
    },
}

# ---------------------------------------------------------------------------
# Tipografia (tamanhos em px)
# ---------------------------------------------------------------------------
FONTE = {
    "familia": "Inter",
    "familia_mono": "JetBrains Mono NL",
    "legenda": 11,
    "pequeno": 12,
    "corpo": 13,
    "subtitulo": 15,
    "titulo": 17,
    "titulo_pagina": 20,
    "titulo_login": 22,
    "metrica": 24,
    "marca_lateral": 19,   # nome do app na barra lateral (marca tipográfica)
    "marca_login": 30,     # nome do app no login
    "peso_normal": 400,
    "peso_medio": 500,
    "peso_semi": 600,
    "peso_negrito": 700,
}

# ---------------------------------------------------------------------------
# Espaçamento (grade de 4 px) e raios
# ---------------------------------------------------------------------------
ESPACO = {"xxs": 2, "xs": 4, "sm": 8, "md": 12, "lg": 16, "xl": 24, "xxl": 32, "xxxl": 48}

RAIO = {
    "sm": 4,       # campos, botões
    "md": 6,       # cartões, tabelas, diálogos
    "lg": 8,       # painel de login
    "pilula": 10,  # selos (metade da altura)
}

# ---------------------------------------------------------------------------
# Dimensões
# ---------------------------------------------------------------------------
DIMENSAO = {
    "altura_controle": 32,         # botões, campos, combos
    "altura_controle_grande": 40,  # login
    "alvo_minimo": 24,             # WCAG 2.2 (2.5.8): nada clicável menor
    "largura_lateral": 248,
    "altura_cabecalho": 56,
    "altura_item_nav": 32,
    "altura_linha_tabela": 30,
    "altura_selo": 20,
    "borda_foco": 2,
    "icone": 16,
    "icone_medio": 20,
    "icone_grande": 32,
    "largura_formulario": 360,
    "largura_login": 880,
    "altura_login": 520,
    "altura_logo_lateral": 34,
    "altura_logo_login": 104,
}

# ---------------------------------------------------------------------------
# Formatos pt-BR
# ---------------------------------------------------------------------------
FORMATO = {
    "data": "%d/%m/%Y",
    "data_hora": "%d/%m/%Y %H:%M",
    "data_hora_seg": "%d/%m/%Y %H:%M:%S",
    "hora": "%H:%M",
    "separador_decimal": ",",
    "separador_milhar": ".",
}

# Perfil -> (rótulo, tom do selo)
PERFIS = {
    "master": ("Master", "info"),
    "cadastro": ("Cadastro", "sucesso"),
    "leitura": ("Leitura", "neutro"),
}

MODOS = ("claro", "escuro")


def cores(modo: str) -> dict[str, str]:
    """Cores de interface do tema `modo` ("claro" ou "escuro"): base + marca."""
    return {**CORES[_modo_valido(modo)], **_cores_marca[modo]}


def cores_grafico(modo: str) -> dict:
    return GRAFICO[_modo_valido(modo)]


def _modo_valido(modo: str) -> str:
    if modo not in CORES:
        raise ValueError(f'tema desconhecido: {modo!r} (use "claro" ou "escuro")')
    return modo
