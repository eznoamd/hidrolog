"""Contêiner que embute uma Figure do matplotlib, com barra de ferramentas."""

from __future__ import annotations

from pathlib import Path

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure
from PySide6.QtCore import QPointF, QSize, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import (
    QAbstractScrollArea, QApplication, QFrame, QHBoxLayout, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget,
)

from ..tema import DIMENSAO, ESPACO, gerenciador, icone, modo_atual
from ..tema.graficos import harmonizar_figura
from .base import rotulo
from .vazio import EstadoVazio


class _BarraGrafico(NavigationToolbar2QT):
    """Barra do matplotlib só com o essencial e textos em português."""

    toolitems = [
        ("Home", "Voltar à visão inicial", "home", "home"),
        ("Back", "Visão anterior", "back", "back"),
        ("Forward", "Próxima visão", "forward", "forward"),
        (None, None, None, None),
        ("Pan", "Arrastar (botão esquerdo) e ampliar eixos (botão direito)", "move", "pan"),
        ("Zoom", "Ampliar uma região", "zoom_to_rect", "zoom"),
        (None, None, None, None),
        ("Save", "Salvar a figura como imagem", "filesave", "save_figure"),
    ]
    _LUCIDE = {"home": "house", "back": "arrow-left", "forward": "arrow-right",
               "move": "move", "zoom_to_rect": "zoom-in", "filesave": "save"}

    def _icon(self, name):
        """Troca os ícones do matplotlib pelos Lucide do app, na cor do tema."""
        return icone(self._LUCIDE.get(Path(name).stem.replace("_large", ""), "chevron-right"),
                     "texto_secundario", cor_ativo="primaria_texto")

    def atualizar_icones(self):
        for acao in self.actions():
            for nome, _, imagem, metodo in self.toolitems:
                if nome and acao.text() == nome:
                    acao.setIcon(self._icon(imagem + ".png"))


class _Canvas(FigureCanvasQTAgg):
    """Canvas que não fica com a roda do mouse: os gráficos não usam a roda
    (o zoom é pela barra de ferramentas), então ela passa para a página, que
    continua rolando com o ponteiro em cima do gráfico."""

    def wheelEvent(self, evento):
        # entrega o giro à área de rolagem mais próxima (o Qt 6 só repassa aos
        # pais eventos "espontâneos"; assim funciona do mesmo jeito sempre)
        pai = self.parentWidget()
        while pai is not None and not isinstance(pai, QAbstractScrollArea):
            pai = pai.parentWidget()
        if pai is None:
            evento.ignore()
            return
        alvo = pai.viewport()
        posicao = QPointF(alvo.mapFromGlobal(evento.globalPosition().toPoint()))
        QApplication.sendEvent(alvo, QWheelEvent(
            posicao, evento.globalPosition(), evento.pixelDelta(), evento.angleDelta(), evento.buttons(),
            evento.modifiers(), evento.phase(), evento.inverted()))
        evento.accept()


class FiguraIncorporada(QFrame):
    """Mostra uma matplotlib.figure.Figure dentro do app, já no tema atual.

        f = FiguraIncorporada(titulo="Série temporal")
        f.definir_figura(graficos.grafico_serie_temporal(dados))

    A figura é recolorida (harmonizar_figura) agora e a cada troca de tema.
    altura_minima: para figuras altas (4–5 painéis) dentro de páginas roláveis.
    """

    def __init__(self, figura: Figure | None = None, titulo: str | None = None,
                 barra_ferramentas: bool = True, altura_minima: int = 360,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.setProperty("papel", "cartao")
        self._barra_ativa = barra_ferramentas
        self._altura_minima = altura_minima
        self.figura: Figure | None = None
        self.canvas: FigureCanvasQTAgg | None = None
        self.barra: _BarraGrafico | None = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(ESPACO["xs"], ESPACO["xs"], ESPACO["xs"], ESPACO["xs"])
        lay.setSpacing(0)
        self._topo = QHBoxLayout()
        self._topo.setContentsMargins(ESPACO["md"], ESPACO["xs"], ESPACO["xs"], 0)
        self._topo.setSpacing(ESPACO["sm"])
        self.titulo = rotulo(titulo or "", "titulo_cartao")
        self.titulo.setVisible(bool(titulo))
        self._topo.addWidget(self.titulo)
        self._topo.addStretch(1)
        lay.addLayout(self._topo)

        self._pilha = QStackedWidget()
        self.vazio = EstadoVazio("Sem dados para o gráfico", "Escolha um período com leituras.", "chart-line")
        self._pilha.addWidget(self.vazio)
        lay.addWidget(self._pilha, 1)
        self.setMinimumHeight(altura_minima)
        if figura is not None:
            self.definir_figura(figura)
        gerenciador().tema_alterado.connect(self._ao_mudar_tema)

    def definir_figura(self, figura: Figure | None) -> None:
        """Troca a figura mostrada (None mostra o estado vazio)."""
        if self.canvas is not None:
            self._pilha.removeWidget(self.canvas)
            self.canvas.deleteLater()
            self.canvas = None
        if self.barra is not None:
            # sai do layout e some já: o deleteLater só roda no próximo ciclo de eventos,
            # e até lá a barra antiga apareceria ao lado da nova
            self._topo.removeWidget(self.barra)
            self.barra.hide()
            self.barra.deleteLater()
            self.barra = None
        self.figura = figura
        if figura is None:
            self._pilha.setCurrentWidget(self.vazio)
            return
        harmonizar_figura(figura, modo_atual())
        self.canvas = _Canvas(figura)
        self.canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.canvas.setMinimumHeight(self._altura_minima - 48)
        self.canvas.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self._pilha.addWidget(self.canvas)
        self._pilha.setCurrentWidget(self.canvas)
        if self._barra_ativa:
            self.barra = _BarraGrafico(self.canvas, self, coordinates=True)
            self.barra.setObjectName("BarraGrafico")
            self.barra.setIconSize(QSize(DIMENSAO["icone"], DIMENSAO["icone"]))
            self._topo.addWidget(self.barra)

    def definir_vazio(self, titulo: str, descricao: str = "") -> None:
        self.vazio.titulo.setText(titulo)
        self.vazio.descricao.setText(descricao)
        self.vazio.descricao.setVisible(bool(descricao))
        self.definir_figura(None)

    def _ao_mudar_tema(self, modo: str):
        if self.figura is not None and self.canvas is not None:
            harmonizar_figura(self.figura, modo)
            self.canvas.draw_idle()
            if self.barra is not None:
                self.barra.atualizar_icones()
