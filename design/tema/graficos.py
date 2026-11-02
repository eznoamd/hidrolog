"""
Estilo dos gráficos (matplotlib) coerente com o app.

Duas camadas, ambas sem mexer no código que desenha o gráfico (o do plugin):

1. rcParams (aplicar_estilo_matplotlib / os arquivos .mplstyle): fonte Inter,
   ciclo de cores da paleta, grade discreta, fundo e textos do tema. Vale para
   toda figura criada depois. aplicar_tema() já chama isto.

2. harmonizar_figura(fig, modo): recolore uma figura JÁ criada. Necessário
   porque bibliotecas de gráficos usam cores fixas ("tab:green", "tab:red",
   "tab:orange", "r-", color="gray") que o rcParams não alcança, e para trocar
   o tema de uma figura aberta sem recalculá-la. FiguraIncorporada chama isto
   automaticamente.

    from design.tema.graficos import aplicar_estilo_matplotlib, harmonizar_figura
    aplicar_estilo_matplotlib("claro")
    fig = desenhar_serie(dados)          # qualquer função que devolve uma Figure
    harmonizar_figura(fig, "claro")
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import matplotlib
from matplotlib import colors as mcolors
from matplotlib import font_manager
from matplotlib.collections import Collection, QuadMesh
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from matplotlib.text import Text

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import tokens  # type: ignore
else:
    from . import tokens

# a busca de peso 'semibold' no DejaVu (reserva) gera avisos inofensivos
logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)

PASTA_FONTES = Path(__file__).resolve().parent / "fontes"
_fontes_registradas = False

# cores fixas comuns em código matplotlib -> índice categórico
_TAB = ["tab:blue", "tab:orange", "tab:green", "tab:purple", "tab:red", "tab:gray"]
_EXTRAS = {"r": 4, "red": 4, "b": 0, "blue": 0, "g": 2, "green": 2, "C0": 0, "C1": 1, "C2": 2, "C3": 3}


def _hex(c) -> str:
    return mcolors.to_hex(c, keep_alpha=False).lower()


def _mapa_categorico() -> dict[str, int]:
    mapa: dict[str, int] = {}
    for i, nome in enumerate(_TAB):
        mapa[_hex(nome)] = i
    for nome, i in _EXTRAS.items():
        if not nome.startswith("C"):
            mapa.setdefault(_hex(nome), i)
    for modo in tokens.MODOS:
        for i, c in enumerate(tokens.cores_grafico(modo)["categoricas"]):
            mapa[_hex(c)] = i
    # ciclo padrão do matplotlib (tab10) além dos 6 primeiros
    return mapa


_MAPA = _mapa_categorico()


def registrar_fontes_matplotlib() -> None:
    global _fontes_registradas
    if _fontes_registradas:
        return
    for arquivo in PASTA_FONTES.glob("*.ttf"):
        font_manager.fontManager.addfont(str(arquivo))
    _fontes_registradas = True


def rc_params(modo: str = "claro") -> dict:
    """Dicionário de rcParams do tema (o mesmo conteúdo dos .mplstyle)."""
    g = tokens.cores_grafico(modo)
    f = tokens.FONTE
    return {
        "font.family": "sans-serif",
        "font.sans-serif": [f["familia"], "DejaVu Sans"],
        "font.monospace": [f["familia_mono"], "DejaVu Sans Mono"],
        "font.size": 9.0,
        "axes.titlesize": 10.0,
        "axes.titleweight": "semibold",
        "axes.titlelocation": "left",
        "axes.titlepad": 8.0,
        "axes.labelsize": 9.0,
        "axes.labelcolor": g["texto_secundario"],
        "axes.labelpad": 6.0,
        "figure.titlesize": 11.0,
        "figure.titleweight": "semibold",
        "figure.facecolor": g["fundo"],
        "figure.edgecolor": g["fundo"],
        "figure.dpi": 100,
        "figure.constrained_layout.use": True,
        "savefig.facecolor": g["fundo"],
        "savefig.dpi": 150,
        "axes.facecolor": g["fundo_eixos"],
        "axes.edgecolor": g["eixo"],
        "axes.linewidth": 0.8,
        "axes.grid": True,
        "axes.axisbelow": True,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.prop_cycle": matplotlib.cycler(color=g["categoricas"]),
        "axes.titlecolor": g["texto"],
        "grid.color": g["grade"],
        "grid.linewidth": 0.6,
        "grid.alpha": 1.0,
        "lines.linewidth": 1.2,
        "lines.markersize": 4,
        "patch.edgecolor": g["fundo"],
        "text.color": g["texto"],
        "xtick.color": g["eixo"],
        "ytick.color": g["eixo"],
        "xtick.labelcolor": g["texto_secundario"],
        "ytick.labelcolor": g["texto_secundario"],
        "xtick.labelsize": 8.5,
        "ytick.labelsize": 8.5,
        "xtick.major.size": 3,
        "ytick.major.size": 3,
        "legend.frameon": True,
        "legend.framealpha": 0.92,
        "legend.facecolor": g["fundo_eixos"],
        "legend.edgecolor": g["grade"],
        "legend.fontsize": 8.5,
        "legend.labelcolor": g["texto_secundario"],
        "image.cmap": g["mapa_cores"],
        "axes.formatter.use_locale": False,
        "date.autoformatter.day": "%d/%m",
        "date.autoformatter.hour": "%d/%m %H:%M",
        "date.autoformatter.minute": "%H:%M",
        "date.autoformatter.month": "%m/%Y",
    }


def aplicar_estilo_matplotlib(modo: str = "claro") -> None:
    registrar_fontes_matplotlib()
    matplotlib.rcParams.update(rc_params(modo))


def contexto_estilo(modo: str = "claro"):
    """`with contexto_estilo("escuro"): fig = ...` (não altera o global)."""
    registrar_fontes_matplotlib()
    return matplotlib.rc_context(rc_params(modo))


# ---------------------------------------------------------------------------
# Recolorir uma figura pronta
# ---------------------------------------------------------------------------
def _papel_cor(rgba, padrao: str) -> tuple:
    """Classifica uma cor original: ("cat", i) | ("texto",) | ("sec",) | ("fixo", hex)."""
    if rgba is None:
        return ("fixo", None)
    try:
        hx = _hex(rgba)
    except (ValueError, TypeError):
        return ("fixo", None)
    if hx in _MAPA:
        return ("cat", _MAPA[hx])
    if hx in ("#000000",) or hx in {_hex(tokens.cores_grafico(m)["texto"]) for m in tokens.MODOS}:
        return ("texto",)
    if hx in ("#808080", "#7f7f7f") or hx in {_hex(tokens.cores_grafico(m)["texto_secundario"]) for m in tokens.MODOS}:
        return ("sec",)
    return ("fixo", hx) if padrao == "fixo" else (padrao,)


def _resolver(papel: tuple, g: dict):
    tipo = papel[0]
    if tipo == "cat":
        return g["categoricas"][papel[1] % len(g["categoricas"])]
    if tipo == "texto":
        return g["texto"]
    if tipo == "sec":
        return g["texto_secundario"]
    return papel[1]


def _guardar(obj, chave: str, calcular):
    nome = f"_hidrolog_{chave}"
    if not hasattr(obj, nome):
        setattr(obj, nome, calcular())
    return getattr(obj, nome)


def harmonizar_figura(fig: Figure, modo: str = "claro") -> Figure:
    """Ajusta uma Figure já pronta ao tema `modo` (cores, fundo, textos,
    grade, eixos e fonte). Pode ser chamada de novo para trocar o tema."""
    registrar_fontes_matplotlib()
    g = tokens.cores_grafico(modo)
    fam = [tokens.FONTE["familia"], "DejaVu Sans"]

    fig.set_facecolor(g["fundo"])
    fig.set_edgecolor(g["fundo"])

    for ax in fig.axes:
        ax.set_facecolor(g["fundo_eixos"])
        eh_colorbar = hasattr(ax, "_colorbar") or ax.get_label() == "<colorbar>"
        for nome, spine in ax.spines.items():
            spine.set_color(g["eixo"])
            spine.set_linewidth(0.8)
            if not eh_colorbar and nome in ("top", "right") and not _eh_eixo_gemeo(ax, nome):
                spine.set_visible(False)
        ax.tick_params(which="major", color=g["eixo"], labelcolor=g["texto_secundario"],
                       grid_color=g["grade"], grid_alpha=1.0, grid_linewidth=0.6)
        ax.tick_params(which="minor", color=g["eixo"], labelcolor=g["texto_secundario"],
                       grid_color=g["grade"], grid_alpha=0.45, grid_linewidth=0.5)
        ax.set_axisbelow(True)

        for linha in ax.get_lines():
            papel = _guardar(linha, "papel", lambda l=linha: _papel_cor(l.get_color(), "fixo"))
            cor = _resolver(papel, g)
            if cor is not None:
                linha.set_color(cor)
                linha.set_markerfacecolor(cor)
                linha.set_markeredgecolor(cor)

        for patch in ax.patches:
            papel = _guardar(patch, "papel", lambda p=patch: _papel_cor(p.get_facecolor(), "fixo"))
            cor = _resolver(papel, g)
            if cor is not None:
                alfa = patch.get_alpha()
                patch.set_facecolor(cor)
                if alfa is not None and alfa < 0.5:  # faixas sombreadas (eventos)
                    patch.set_alpha(g["sombreado_alfa"])

        for col in ax.collections:
            if isinstance(col, QuadMesh):
                cmap = col.get_cmap().copy()
                cmap.set_bad((0, 0, 0, 0))
                col.set_cmap(cmap)
                continue
            fc = col.get_facecolor()
            papel = _guardar(col, "papel", lambda c=fc: _papel_cor(c[0] if len(c) else None, "fixo"))
            cor = _resolver(papel, g)
            if cor is not None:
                alfa = col.get_alpha()
                col.set_facecolor(cor)
                if alfa is not None and alfa < 0.5:
                    col.set_alpha(g["sombreado_alfa"])

        leg = ax.get_legend()
        if leg is not None:
            moldura = leg.get_frame()
            moldura.set_facecolor(g["fundo_eixos"])
            moldura.set_edgecolor(g["grade"])
            moldura.set_alpha(0.92)
            for alca in getattr(leg, "legend_handles", getattr(leg, "legendHandles", [])):
                if isinstance(alca, Line2D):
                    papel = _guardar(alca, "papel", lambda a=alca: _papel_cor(a.get_color(), "fixo"))
                    cor = _resolver(papel, g)
                    if cor is not None:
                        alca.set_color(cor)
                elif isinstance(alca, (Patch, Collection)) and hasattr(alca, "set_facecolor"):
                    fc = alca.get_facecolor()
                    fc = fc[0] if (hasattr(fc, "__len__") and len(fc) and hasattr(fc[0], "__len__")) else fc
                    papel = _guardar(alca, "papel", lambda c=fc: _papel_cor(c, "fixo"))
                    cor = _resolver(papel, g)
                    if cor is not None:
                        alca.set_facecolor(cor)

    for texto in fig.findobj(Text):
        papel = _guardar(texto, "papel", lambda t=texto: _papel_cor(t.get_color(), "texto"))
        texto.set_color(_resolver(papel, g))
        texto.set_fontfamily(fam)

    # títulos e rótulos dos eixos com a hierarquia do app
    if fig._suptitle is not None:
        fig._suptitle.set_fontweight("semibold")
        fig._suptitle.set_fontsize(11)
    for ax in fig.axes:
        for rot in (ax.xaxis.label, ax.yaxis.label):
            papel = getattr(rot, "_hidrolog_papel", ("texto",))
            if papel[0] == "texto":
                rot.set_color(g["texto_secundario"])
    return fig


def _eh_eixo_gemeo(ax, lado: str) -> bool:
    """twinx usa a borda direita: não esconder."""
    if lado != "right":
        return False
    return ax.yaxis.get_label_position() == "right" or ax.yaxis.get_ticks_position() == "right"


# ---------------------------------------------------------------------------
# Arquivos .mplstyle
# ---------------------------------------------------------------------------
def gerar_mplstyle(pasta: Path | None = None) -> list[Path]:
    """Grava graficos-claro.mplstyle e graficos-escuro.mplstyle (para usar fora
    do app: plt.style.use("caminho/graficos-claro.mplstyle"))."""
    pasta = pasta or Path(__file__).resolve().parent
    saidas = []
    for modo in tokens.MODOS:
        linhas = [f"# Hidrolog — estilo matplotlib, tema {modo} (gerado de tokens.py)",
                  "# A fonte Inter precisa estar instalada ou registrada (registrar_fontes_matplotlib)."]
        for chave, valor in rc_params(modo).items():
            if chave == "axes.prop_cycle":
                cores = ", ".join(f"'{c.lstrip('#')}'" for c in tokens.cores_grafico(modo)["categoricas"])
                valor = f"cycler('color', [{cores}])"
            elif isinstance(valor, list):
                valor = ", ".join(valor)
            elif isinstance(valor, str) and valor.startswith("#"):
                valor = valor.lstrip("#")
            elif isinstance(valor, str) and "%" in valor:
                valor = valor
            linhas.append(f"{chave}: {valor}")
        destino = pasta / f"graficos-{modo}.mplstyle"
        destino.write_text("\n".join(linhas) + "\n", encoding="utf-8")
        saidas.append(destino)
    return saidas


if __name__ == "__main__":
    for p in gerar_mplstyle():
        print("gravado", p)
