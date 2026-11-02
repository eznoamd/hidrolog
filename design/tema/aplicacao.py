"""Aplicação do tema na QApplication: fontes, paleta, QSS, ícones."""

from __future__ import annotations

import atexit
import shutil
import tempfile
from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QByteArray, QLibraryInfo, QLocale, QObject, QRectF, Qt, QTranslator, Signal
from PySide6.QtGui import QColor, QFont, QFontDatabase, QIcon, QPainter, QPalette, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication, QWidget

from . import tokens
from .qss import gerar_qss

PASTA_DESIGN = Path(__file__).resolve().parent.parent
PASTA_FONTES = Path(__file__).resolve().parent / "fontes"
PASTA_ICONES = PASTA_DESIGN / "assets" / "icones"


class _GerenciadorTema(QObject):
    """Guarda o tema atual e avisa os componentes quando ele muda."""

    tema_alterado = Signal(str)

    def __init__(self):
        super().__init__()
        self.modo = "claro"
        self._pasta_cache: Path | None = None

    def pasta_cache(self) -> Path:
        if self._pasta_cache is None:
            self._pasta_cache = Path(tempfile.mkdtemp(prefix="hidrolog-tema-"))
            # imagens que o QSS usa (setas, marcas); somem quando o processo termina
            atexit.register(shutil.rmtree, self._pasta_cache, ignore_errors=True)
        return self._pasta_cache


_gerenciador: _GerenciadorTema | None = None
_fontes_carregadas = False


def gerenciador() -> _GerenciadorTema:
    global _gerenciador
    if _gerenciador is None:
        _gerenciador = _GerenciadorTema()
    return _gerenciador


def modo_atual() -> str:
    return gerenciador().modo


def cor(nome: str, modo: str | None = None) -> str:
    """Hex do token `nome` no tema atual (ou em `modo`). Aceita também '#hex'."""
    if nome.startswith("#"):
        return nome
    return tokens.cores(modo or modo_atual())[nome]


# ---------------------------------------------------------------------------
# Fontes
# ---------------------------------------------------------------------------
def carregar_fontes() -> None:
    """Registra Inter e JetBrains Mono NL (tema/fontes) no QFontDatabase."""
    global _fontes_carregadas
    if _fontes_carregadas:
        return
    for arquivo in sorted(PASTA_FONTES.glob("*.ttf")):
        if QFontDatabase.addApplicationFont(str(arquivo)) < 0:
            print(f"[tema] não consegui carregar a fonte {arquivo.name}")
    _fontes_carregadas = True


def fonte(tamanho: int | None = None, peso: int | None = None) -> QFont:
    f = QFont(tokens.FONTE["familia"])
    f.setPixelSize(tamanho or tokens.FONTE["corpo"])
    f.setWeight(QFont.Weight(peso or tokens.FONTE["peso_normal"]))
    f.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    return f


def fonte_mono(tamanho: int | None = None, peso: int | None = None) -> QFont:
    f = QFont(tokens.FONTE["familia_mono"])
    f.setStyleHint(QFont.StyleHint.Monospace)
    f.setPixelSize(tamanho or tokens.FONTE["corpo"])
    f.setWeight(QFont.Weight(peso or tokens.FONTE["peso_normal"]))
    return f


# ---------------------------------------------------------------------------
# Ícones (Lucide, assets/icones, traço em currentColor)
# ---------------------------------------------------------------------------
@lru_cache(maxsize=None)
def _svg(nome: str) -> str:
    caminho = PASTA_ICONES / f"{nome}.svg"
    if not caminho.exists():
        raise FileNotFoundError(f"ícone {nome!r} não está em {PASTA_ICONES}")
    return caminho.read_text(encoding="utf-8")


@lru_cache(maxsize=512)
def _pixmap(nome: str, hexa: str, tamanho: int, escala: float) -> QPixmap:
    svg = _svg(nome).replace("currentColor", hexa)
    renderizador = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    lado = round(tamanho * escala)
    pm = QPixmap(lado, lado)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderizador.render(p, QRectF(0, 0, lado, lado))
    p.end()
    pm.setDevicePixelRatio(escala)
    return pm


def pixmap_icone(nome: str, cor_icone: str = "texto_secundario", tamanho: int | None = None) -> QPixmap:
    tamanho = tamanho or tokens.DIMENSAO["icone"]
    app = QApplication.instance()
    escala = max(2.0, app.devicePixelRatio() if app else 1.0)
    return _pixmap(nome, cor(cor_icone), tamanho, escala)


def icone(nome: str, cor_icone: str = "texto_secundario", tamanho: int | None = None,
          cor_desabilitado: str = "texto_desabilitado", cor_ativo: str | None = None) -> QIcon:
    """QIcon de um ícone Lucide na cor de um token (ou hex). `cor_ativo` é a
    cor no estado marcado (checked), útil na navegação."""
    ic = QIcon()
    ic.addPixmap(pixmap_icone(nome, cor_icone, tamanho), QIcon.Mode.Normal, QIcon.State.Off)
    ic.addPixmap(pixmap_icone(nome, cor_desabilitado, tamanho), QIcon.Mode.Disabled, QIcon.State.Off)
    if cor_ativo:
        ic.addPixmap(pixmap_icone(nome, cor_ativo, tamanho), QIcon.Mode.Normal, QIcon.State.On)
    return ic


def _gravar_svg_tema(nome: str, hexa: str, modo: str) -> str:
    """Grava um ícone recolorido em disco (o QSS só aceita url de arquivo)."""
    pasta = gerenciador().pasta_cache() / modo
    pasta.mkdir(parents=True, exist_ok=True)
    destino = pasta / f"{nome}-{hexa.lstrip('#')}.svg"
    if not destino.exists():
        destino.write_text(_svg(nome).replace("currentColor", hexa), encoding="utf-8")
    return destino.as_posix()


def _imagens_qss(modo: str) -> dict[str, str]:
    c = tokens.cores(modo)
    return {
        "seta_baixo": _gravar_svg_tema("chevron-down", c["texto_secundario"], modo),
        "seta_baixo_desab": _gravar_svg_tema("chevron-down", c["texto_desabilitado"], modo),
        "marca": _gravar_svg_tema("check", c["texto_sobre_primaria"], modo),
    }


# ---------------------------------------------------------------------------
# Paleta Qt (widgets nativos, NavigationToolbar do matplotlib etc.)
# ---------------------------------------------------------------------------
def _paleta(modo: str) -> QPalette:
    c = tokens.cores(modo)
    p = QPalette()
    R = QPalette.ColorRole
    G = QPalette.ColorGroup
    p.setColor(R.Window, QColor(c["fundo"]))
    p.setColor(R.WindowText, QColor(c["texto"]))
    p.setColor(R.Base, QColor(c["superficie"]))
    p.setColor(R.AlternateBase, QColor(c["superficie_alt"]))
    p.setColor(R.Text, QColor(c["texto"]))
    p.setColor(R.Button, QColor(c["superficie"]))
    p.setColor(R.ButtonText, QColor(c["texto"]))
    p.setColor(R.Highlight, QColor(c["selecao"]))
    p.setColor(R.HighlightedText, QColor(c["texto"]))
    p.setColor(R.ToolTipBase, QColor(c["superficie_elevada"]))
    p.setColor(R.ToolTipText, QColor(c["texto"]))
    p.setColor(R.PlaceholderText, QColor(c["texto_terciario"]))
    p.setColor(R.Link, QColor(c["primaria_texto"]))
    p.setColor(R.Mid, QColor(c["borda"]))
    p.setColor(R.Light, QColor(c["superficie"]))
    p.setColor(R.Dark, QColor(c["borda_forte"]))
    for papel in (R.WindowText, R.Text, R.ButtonText):
        p.setColor(G.Disabled, papel, QColor(c["texto_desabilitado"]))
    return p


def instalar_traducao_qt(app: QApplication) -> None:
    """Textos padrão do Qt (diálogos de arquivo e de mensagem, menus de
    contexto) em português do Brasil. Instala uma vez por aplicação."""
    if getattr(app, "_hidrolog_traducao", None) is not None:
        return
    tradutor = QTranslator(app)
    pasta = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    if tradutor.load(QLocale(QLocale.Language.Portuguese, QLocale.Country.Brazil), "qtbase", "_", pasta):
        app.installTranslator(tradutor)
    app._hidrolog_traducao = tradutor


def aplicar_tema(app: QApplication, modo: str = "claro") -> None:
    """Aplica o tema `modo` ("claro" ou "escuro") à aplicação inteira:
    tradução do Qt, fontes embarcadas, estilo Fusion, paleta, QSS e estilo do
    matplotlib."""
    tokens.cores(modo)  # valida
    instalar_traducao_qt(app)
    carregar_fontes()
    if app.style().name().lower() != "fusion":
        app.setStyle("Fusion")
    app.setFont(fonte())
    app.setPalette(_paleta(modo))
    app.setStyleSheet(gerar_qss(modo, _imagens_qss(modo)))
    if app.windowIcon().isNull():
        app.setWindowIcon(icone_aplicativo())
    try:
        from .graficos import aplicar_estilo_matplotlib
        aplicar_estilo_matplotlib(modo)
    except ImportError:  # matplotlib é opcional para o tema
        pass
    g = gerenciador()
    g.modo = modo
    g.tema_alterado.emit(modo)


def icone_aplicativo() -> QIcon:
    """Ícone da janela: marca.icone_app; sem ele, a própria logo (provisório)."""
    from .marca import marca_atual
    m = marca_atual()
    caminho = m.icone_app or m.logo
    return QIcon(str(caminho)) if caminho else QIcon()


def alternar_tema(app: QApplication) -> str:
    novo = "escuro" if modo_atual() == "claro" else "claro"
    aplicar_tema(app, novo)
    return novo


def repolir(widget: QWidget) -> None:
    """Reaplica o QSS depois de mudar uma propriedade dinâmica (setProperty)."""
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()
