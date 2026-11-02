"""
Usuário no cabeçalho: avatar com as iniciais, nome e perfil; um clique abre o
menu da conta (Minha conta, Sair).

    menu = MenuUsuario()
    menu.definir_usuario("Ana Souza", "cadastro", "ana")
    menu.minha_conta_solicitada.connect(...)
    menu.sair_solicitado.connect(...)

    Avatar("Ana Souza", 40)        # só o círculo com as iniciais
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ..tema import DIMENSAO, ESPACO, FONTE, PERFIS, cor, fonte, gerenciador, icone, repolir
from .base import Divisoria, rotulo


def iniciais(nome: str) -> str:
    """Primeira letra do primeiro e do último nome ("Ana de Souza" -> "AS")."""
    partes = [p for p in (nome or "").split() if p[:1].isalnum()]
    if not partes:
        return "?"
    if len(partes) == 1:
        return partes[0][:2].upper()
    return (partes[0][0] + partes[-1][0]).upper()


def nome_perfil(perfil: str) -> str:
    return PERFIS.get(perfil, (perfil.capitalize(), "neutro"))[0]


class Avatar(QWidget):
    """Círculo na cor de ação do tema com as iniciais do nome."""

    def __init__(self, nome: str = "", tamanho: int = 32, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedSize(tamanho, tamanho)
        self._iniciais = iniciais(nome)
        gerenciador().tema_alterado.connect(self._tema_alterado)

    def _tema_alterado(self, *_):
        self.update()

    def definir_nome(self, nome: str) -> None:
        self._iniciais = iniciais(nome)
        self.update()

    @property
    def texto(self) -> str:
        return self._iniciais

    def paintEvent(self, _evento):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(cor("primaria")))
        p.drawEllipse(QRectF(self.rect()))
        p.setPen(QColor(cor("texto_sobre_primaria")))
        p.setFont(fonte(max(10, round(self.height() * 0.38)), FONTE["peso_semi"]))
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._iniciais)
        p.end()


class _ItemMenu(QPushButton):
    def __init__(self, texto: str, nome_icone: str, perigo: bool = False):
        super().__init__(" " + texto)
        self.setObjectName("ItemMenuUsuario")
        self.setProperty("perigo", "true" if perigo else "false")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName(texto)
        self._icone = nome_icone
        self._perigo = perigo
        self.atualizar_icone()

    def atualizar_icone(self) -> None:
        self.setIcon(icone(self._icone, "erro" if self._perigo else "texto_secundario"))
        self.setIconSize(QSize(DIMENSAO["icone"], DIMENSAO["icone"]))


class PainelUsuario(QFrame):
    """O menu que abre abaixo do MenuUsuario (janela popup: fecha ao clicar fora).
    Só as ações: o nome e o perfil já estão no botão, ao lado da seta."""

    minha_conta = Signal()
    sair = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setObjectName("PainelUsuario")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setMinimumWidth(240)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(ESPACO["xs"], ESPACO["xs"], ESPACO["xs"], ESPACO["xs"])
        lay.setSpacing(ESPACO["xs"])
        self.item_conta = _ItemMenu("Minha conta", "user")
        lay.addWidget(self.item_conta)
        lay.addWidget(Divisoria())
        self.item_sair = _ItemMenu("Sair", "log-out", perigo=True)
        lay.addWidget(self.item_sair)
        self.item_conta.clicked.connect(lambda: self._escolher(self.minha_conta))
        self.item_sair.clicked.connect(lambda: self._escolher(self.sair))
        gerenciador().tema_alterado.connect(self._tema_alterado)

    def _tema_alterado(self, *_):
        for item in (self.item_conta, self.item_sair):
            item.atualizar_icone()

    def _escolher(self, sinal) -> None:
        self.hide()
        sinal.emit()

    def abrir_abaixo_de(self, botao: QWidget) -> None:
        self.adjustSize()
        largura = max(self.sizeHint().width(), botao.width())
        self.resize(largura, self.sizeHint().height())
        self.move(botao.mapToGlobal(QPoint(botao.width() - largura, botao.height() + ESPACO["xs"])))
        self.show()


class MenuUsuario(QPushButton):
    """Botão do usuário no cabeçalho (avatar, nome, perfil, seta) que abre o PainelUsuario."""

    minha_conta_solicitada = Signal()
    sair_solicitado = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("MenuUsuario")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(ESPACO["xs"], ESPACO["xs"], ESPACO["sm"], ESPACO["xs"])
        lay.setSpacing(ESPACO["sm"])
        self.avatar = Avatar("", 32)
        lay.addWidget(self.avatar)
        textos = QVBoxLayout()
        textos.setSpacing(0)
        self.nome = rotulo("", None)
        self.nome.setProperty("peso", "semi")
        self.subtitulo = rotulo("", "legenda")
        textos.addWidget(self.nome)
        textos.addWidget(self.subtitulo)
        lay.addLayout(textos)
        self.seta = QLabel()
        lay.addWidget(self.seta)
        for w in (self.avatar, self.nome, self.subtitulo, self.seta):
            w.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.painel = PainelUsuario(self)
        self.painel.minha_conta.connect(self.minha_conta_solicitada)
        self.painel.sair.connect(self.sair_solicitado)
        self.clicked.connect(self.abrir)
        gerenciador().tema_alterado.connect(self._tema_alterado)
        self._tema_alterado()

    def _tema_alterado(self, *_):
        self.seta.setPixmap(icone("chevron-down", "texto_terciario", 14).pixmap(14, 14))
        repolir(self.nome)

    def definir_usuario(self, nome: str, perfil: str, login: str = "") -> None:
        self.nome.setText(nome)
        self.subtitulo.setText(nome_perfil(perfil))
        self.avatar.definir_nome(nome)
        self.setAccessibleName(f"{nome}, {nome_perfil(perfil)}: menu da conta")
        self.setToolTip(f"{nome} ({login})" if login else nome)
        self.updateGeometry()

    def abrir(self) -> None:
        self.painel.abrir_abaixo_de(self)

    def sizeHint(self) -> QSize:
        return self.layout().sizeHint()

    def minimumSizeHint(self) -> QSize:
        return self.layout().minimumSize()
