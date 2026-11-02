"""
Logo do laboratório e da instituição (lidas de tema.marca).

As imagens vêm da pasta de marca da instalação (ver tema/marca.py). Sem
imagem, cada uma mostra o texto "LOGO" num quadro tracejado: o app instalado
sem marca fica genérico e mostra onde a logo entra.

No tema escuro é usada Marca.logo_escura, se existir (ver
gerar_logo_escura.py); sem ela, a logo normal vai sobre uma placa branca
(token MARCA["placa"]).
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QByteArray, QRectF, QSize, Qt
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication, QFrame, QLabel, QVBoxLayout, QWidget

from ..tema import ESPACO, FONTE, gerenciador, modo_atual
from ..tema.marca import marca_atual
from .base import rotulo


def caminho_logo(modo: str | None = None) -> Path | None:
    """Arquivo da logo da marca atual para o tema `modo` (padrão: o atual):
    a versão escura no tema escuro, quando existir. None se não houver logo."""
    m = marca_atual()
    if (modo or modo_atual()) == "escuro" and m.logo_escura is not None:
        return m.logo_escura
    return m.logo


def carregar_imagem(caminho: Path, altura: int) -> QPixmap:
    """Pixmap nítido (HiDPI) com `altura` px lógicos, de .svg ou .png."""
    app = QApplication.instance()
    escala = max(2.0, app.devicePixelRatio() if app else 1.0)
    if caminho.suffix.lower() == ".svg":
        r = QSvgRenderer(QByteArray(caminho.read_bytes()))
        tam = r.defaultSize()
        largura = round(altura * tam.width() / max(tam.height(), 1))
        pm = QPixmap(round(largura * escala), round(altura * escala))
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r.render(p, QRectF(0, 0, pm.width(), pm.height()))
        p.end()
    else:
        pm = QPixmap(str(caminho)).scaledToHeight(round(altura * escala), Qt.TransformationMode.SmoothTransformation)
    pm.setDevicePixelRatio(escala)
    return pm


class _Imagem(QLabel):
    def __init__(self, caminho: Path, altura: int):
        super().__init__()
        self.setPixmap(carregar_imagem(caminho, altura))
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)


class LogoMarca(QFrame):
    """Logo do laboratório (marca atual).

    altura: altura da imagem em px.
    placa: "auto" (placa branca só no tema escuro e só se não houver
           logo_escura), True (sempre) ou False.
    caminho: força um arquivo (senão usa assets/logo.svg|png, ou
             assets/logo-escura.png no tema escuro).
    """

    def __init__(self, altura: int = 40, placa: bool | str = "auto", caminho: str | Path | None = None,
                 alinhamento=Qt.AlignmentFlag.AlignLeft, parent: QWidget | None = None):
        super().__init__(parent)
        self._altura = altura
        self._placa = placa
        self._caminho = Path(caminho) if caminho else None
        self._alinhamento = alinhamento
        m = marca_atual()
        self.setAccessibleName(f"Logo do {m.laboratorio}" if m.laboratorio else "Logo do laboratório")
        self.setToolTip(m.laboratorio_completo or "")
        self._lay = QVBoxLayout(self)
        self._lay.setSpacing(0)
        self._conteudo: QWidget | None = None
        self._montar()
        gerenciador().tema_alterado.connect(self._montar)

    @property
    def tem_imagem(self) -> bool:
        return (self._caminho or caminho_logo()) is not None

    def _montar(self, *_):
        if self._conteudo is not None:
            self._lay.removeWidget(self._conteudo)
            self._conteudo.setParent(None)
            self._conteudo.deleteLater()
        caminho = self._caminho or caminho_logo()
        if caminho is not None:
            self._conteudo = _Imagem(caminho, self._altura)
        else:
            self._conteudo = reserva_logo(self._altura)
        usar_placa = self._placa is True or (
            self._placa == "auto" and modo_atual() == "escuro" and caminho is not None
            and self._caminho is None and marca_atual().logo_escura is None
            and marca_atual().logo_precisa_placa_no_escuro)
        self.setProperty("papel", "placa_marca" if usar_placa else None)
        m = ESPACO["sm"] if usar_placa else 0
        self._lay.setContentsMargins(m + ESPACO["xs"] * bool(usar_placa), m, m + ESPACO["xs"] * bool(usar_placa), m)
        self._lay.addWidget(self._conteudo, 0, self._alinhamento)
        self.style().unpolish(self)
        self.style().polish(self)

    def sizeHint(self) -> QSize:
        return super().sizeHint()


def reserva_logo(altura: int) -> QLabel:
    """O texto "LOGO" num quadro tracejado, no lugar de uma logo que a
    instalação ainda não pôs na pasta de marca."""
    r = rotulo("LOGO", "logo_reserva")
    r.setAlignment(Qt.AlignmentFlag.AlignCenter)
    r.setFixedHeight(altura)
    r.setMinimumWidth(round(altura * 2.2))
    f = r.font()
    f.setPixelSize(max(FONTE["pequeno"], round(altura * 0.32)))
    f.setWeight(f.Weight.Bold)
    f.setLetterSpacing(f.SpacingType.PercentageSpacing, 120)
    r.setFont(f)
    r.setToolTip("Coloque a logo na pasta de marca da instalação")
    return r


class LogoInstituicao(QFrame):
    """Logo/brasão da instituição (Marca.logo_instituicao), só como assinatura
    institucional discreta (rodapé do login). Sem arquivo, mostra "LOGO"."""

    def __init__(self, altura: int = 40, parent: QWidget | None = None):
        super().__init__(parent)
        m = marca_atual()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        caminho = m.logo_instituicao
        img = _Imagem(caminho, altura) if caminho else reserva_logo(altura)
        lay.addWidget(img)
        self.setAccessibleName(m.instituicao or "Logo da instituição")
        self.setToolTip(m.instituicao or "")

