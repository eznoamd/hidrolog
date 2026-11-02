"""
Indicadores de carregamento: para tudo o que pode demorar (login, abertura do
banco, dados de um período, preparo de um plugin).

    IndicadorCarregamento(tamanho=28)          # o arco que gira (na cor de ação)
    Carregando("Carregando as leituras…")      # indicador + texto, centrado
    s = SobreposicaoCarregamento(widget)       # cobre `widget` enquanto ele espera
    s.mostrar("Buscando os dados…"); s.esconder()

A animação só roda enquanto o indicador está visível.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QVBoxLayout, QWidget

from ..tema import ESPACO, cor, gerenciador
from .base import rotulo

QUADRO_MS = 16          # ~60 quadros por segundo
GRAUS_POR_QUADRO = 6    # uma volta por segundo


class IndicadorCarregamento(QWidget):
    """Um arco que gira, na cor de ação do tema, sobre um anel discreto."""

    def __init__(self, tamanho: int = 28, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedSize(tamanho, tamanho)
        self.setAccessibleName("Carregando")
        self._angulo = 0
        self._timer = QTimer(self)
        self._timer.setInterval(QUADRO_MS)
        self._timer.timeout.connect(self._girar)
        gerenciador().tema_alterado.connect(self._tema_alterado)

    def _tema_alterado(self, *_):
        self.update()

    def _girar(self) -> None:
        self._angulo = (self._angulo + GRAUS_POR_QUADRO) % 360
        self.update()

    @property
    def girando(self) -> bool:
        return self._timer.isActive()

    def showEvent(self, evento):
        self._timer.start()
        super().showEvent(evento)

    def hideEvent(self, evento):
        self._timer.stop()
        super().hideEvent(evento)

    def paintEvent(self, _evento):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        espessura = max(2.0, self.width() / 9)
        r = QRectF(self.rect()).adjusted(espessura, espessura, -espessura, -espessura)
        anel = QColor(cor("primaria"))
        anel.setAlpha(45)
        p.setPen(QPen(anel, espessura))
        p.drawEllipse(r)
        caneta = QPen(QColor(cor("primaria")), espessura)
        caneta.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(caneta)
        p.drawArc(r, -self._angulo * 16, 100 * 16)
        p.end()


class Carregando(QWidget):
    """Indicador + texto, centrados: o estado "carregando" de uma área."""

    def __init__(self, texto: str = "Carregando…", tamanho: int = 32, parent: QWidget | None = None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setSpacing(ESPACO["md"])
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.indicador = IndicadorCarregamento(tamanho)
        lay.addWidget(self.indicador, 0, Qt.AlignmentFlag.AlignHCenter)
        self.texto = rotulo(texto, "secundario")
        self.texto.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.texto)

    def definir_texto(self, texto: str) -> None:
        self.texto.setText(texto)


class SobreposicaoCarregamento(QWidget):
    """Camada que cobre outro widget (fundo do tema, quase opaco) com o
    indicador e uma mensagem, enquanto ele espera dados. Acompanha o tamanho do
    widget coberto e bloqueia os cliques nele."""

    def __init__(self, alvo: QWidget):
        super().__init__(alvo)
        self._alvo = alvo
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAutoFillBackground(False)
        lay = QVBoxLayout(self)
        self.carregando = Carregando()
        lay.addWidget(self.carregando)
        alvo.installEventFilter(self)
        self.hide()

    def eventFilter(self, objeto, evento):
        if objeto is self._alvo and evento.type() == QEvent.Type.Resize:
            self.setGeometry(self._alvo.rect())
        return False

    def mostrar(self, texto: str = "Carregando…") -> None:
        self.carregando.definir_texto(texto)
        self.setGeometry(self._alvo.rect())
        self.raise_()
        self.show()

    def esconder(self) -> None:
        self.hide()

    def paintEvent(self, _evento):
        p = QPainter(self)
        fundo = QColor(cor("fundo"))
        fundo.setAlpha(225)
        p.fillRect(self.rect(), fundo)
        p.end()
