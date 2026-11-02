"""Estado vazio: o que mostrar quando não há dados (ou sem permissão)."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from ..tema import DIMENSAO, ESPACO, gerenciador, pixmap_icone
from .base import Botao, rotulo


class EstadoVazio(QWidget):
    """Ícone + título + explicação + (opcional) uma ação.

    Diga o porquê e o próximo passo: "Nenhum envio ainda" /
    "Importe a pasta do cartão SD para ver as leituras aqui." / [Importar dados].
    """

    acao = Signal()

    def __init__(self, titulo: str, descricao: str = "", nome_icone: str = "inbox",
                 texto_acao: str | None = None, icone_acao: str | None = None,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self._nome_icone = nome_icone
        lay = QVBoxLayout(self)
        lay.setContentsMargins(ESPACO["xl"], ESPACO["xxl"], ESPACO["xl"], ESPACO["xxl"])
        lay.setSpacing(ESPACO["sm"])
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._icone = QLabel()
        self._icone.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self._icone)
        lay.addSpacing(ESPACO["xs"])
        self.titulo = rotulo(titulo, "subtitulo")
        self.titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.titulo)
        self.descricao = rotulo(descricao, "secundario", quebra=True)
        self.descricao.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # largura fixa: o QLabel com quebra só calcula a altura certa com largura definida
        self.descricao.setFixedWidth(DIMENSAO["largura_formulario"] + 60)
        self.descricao.setVisible(bool(descricao))
        lay.addWidget(self.descricao, 0, Qt.AlignmentFlag.AlignHCenter)
        if texto_acao:
            lay.addSpacing(ESPACO["sm"])
            self.botao = Botao(texto_acao, "primaria", icone_acao)
            self.botao.clicked.connect(self.acao)
            lay.addWidget(self.botao, 0, Qt.AlignmentFlag.AlignHCenter)
        self._atualizar()
        gerenciador().tema_alterado.connect(self._atualizar)

    def _atualizar(self, *_):
        self._icone.setPixmap(pixmap_icone(self._nome_icone, "texto_terciario", DIMENSAO["icone_grande"]))
