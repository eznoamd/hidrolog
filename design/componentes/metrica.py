"""Cartão de métrica (KPI): rótulo, valor em fonte mono, unidade e contexto."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from ..tema import DIMENSAO, ESPACO, gerenciador, pixmap_icone
from . import formatos
from .base import rotulo
from .selo import Selo


class CartaoMetrica(QFrame):
    """KPI com unidade sempre visível.

        CartaoMetrica("Chuva acumulada", 132.4, "mm", casas=1,
                      descricao="01/10/2026 – 28/10/2026", nome_icone="cloud-rain")

    `valor` pode ser número (formatado em pt-BR com `casas`) ou texto pronto.
    `selo` (texto, tom) mostra uma situação ao lado do rótulo.
    """

    def __init__(self, titulo: str, valor=None, unidade: str = "", descricao: str = "",
                 casas: int = 1, nome_icone: str | None = None, selo: tuple[str, str] | None = None,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.setProperty("papel", "cartao")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._casas = casas
        self._nome_icone = nome_icone

        lay = QVBoxLayout(self)
        lay.setContentsMargins(ESPACO["lg"], ESPACO["md"] + 2, ESPACO["lg"], ESPACO["md"] + 2)
        lay.setSpacing(ESPACO["xs"])

        topo = QHBoxLayout()
        topo.setSpacing(ESPACO["sm"])
        self._icone = QLabel()
        self._icone.setVisible(bool(nome_icone))
        topo.addWidget(self._icone)
        self.titulo = rotulo(titulo, "rotulo_campo")
        topo.addWidget(self.titulo, 1)
        self.selo = Selo(*(selo or ("", "neutro")))
        self.selo.setVisible(bool(selo))
        topo.addWidget(self.selo)
        topo_w = QWidget()
        topo_w.setLayout(topo)
        topo.setContentsMargins(0, 0, 0, 0)
        topo_w.setFixedHeight(DIMENSAO["altura_selo"])
        lay.addWidget(topo_w)

        linha = QHBoxLayout()
        linha.setSpacing(ESPACO["xs"])
        self.valor = rotulo("", "metrica_valor")
        self.valor.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        linha.addWidget(self.valor, 0, Qt.AlignmentFlag.AlignBaseline)
        self.unidade = rotulo(unidade, "metrica_unidade")
        linha.addWidget(self.unidade, 0, Qt.AlignmentFlag.AlignBaseline)
        linha.addStretch(1)
        lay.addLayout(linha)

        self.descricao = rotulo(descricao, "legenda")
        self.descricao.setVisible(bool(descricao))
        lay.addWidget(self.descricao)

        self.definir_valor(valor)
        self._atualizar_icone()
        gerenciador().tema_alterado.connect(self._atualizar_icone)

    def definir_valor(self, valor, unidade: str | None = None, descricao: str | None = None,
                      selo: tuple[str, str] | None = None) -> None:
        if isinstance(valor, (int, float)) and not isinstance(valor, bool):
            texto = formatos.numero(valor, self._casas)
        else:
            texto = formatos.TRACO if valor in (None, "") else str(valor)
        self.valor.setText(texto)
        if unidade is not None:
            self.unidade.setText(unidade)
        self.unidade.setVisible(bool(self.unidade.text()))
        if descricao is not None:
            self.descricao.setText(descricao)
            self.descricao.setVisible(bool(descricao))
        if selo is not None:
            self.selo.definir(*selo)
            self.selo.setVisible(True)
        nome = f"{self.titulo.text()}: {texto} {self.unidade.text()}".strip()
        self.setAccessibleName(nome)

    def _atualizar_icone(self, *_):
        if self._nome_icone:
            self._icone.setPixmap(pixmap_icone(self._nome_icone, "texto_terciario"))
