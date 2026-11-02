"""Seletor de equipamento + período, usado no topo das páginas de sensor."""

from __future__ import annotations

from datetime import date, datetime

from PySide6.QtCore import QDate, Signal
from PySide6.QtWidgets import QComboBox, QDateEdit, QHBoxLayout, QWidget

from ..tema import ESPACO
from .base import rotulo


def campo_data(valor: date | None, nome: str) -> QDateEdit:
    """QDateEdit dd/mm/aaaa com calendário."""
    d = QDateEdit()
    d.setCalendarPopup(True)
    d.setDisplayFormat("dd/MM/yyyy")
    d.setAccessibleName(nome)
    d.setFixedWidth(118)
    if isinstance(valor, datetime):
        valor = valor.date()
    if valor:
        d.setDate(QDate(valor.year, valor.month, valor.day))
    return d


class SeletorEquipamentoPeriodo(QWidget):
    """[Equipamento ▾]  [dd/mm/aaaa] – [dd/mm/aaaa]

    equipamentos: lista de (identificador, rótulo).
    Emite `alterado(identificador, inicio: date, fim: date)`.
    """

    alterado = Signal(object, object, object)

    def __init__(self, equipamentos: list[tuple[object, str]], inicio: date | None = None,
                 fim: date | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(ESPACO["sm"])
        self.equipamento = QComboBox()
        self.equipamento.setAccessibleName("Equipamento")
        self.equipamento.setMinimumWidth(240)
        for ident, texto in equipamentos:
            self.equipamento.addItem(texto, ident)
        lay.addWidget(self.equipamento)
        lay.addSpacing(ESPACO["xs"])
        self.inicio = self._data(inicio, "Início do período")
        self.fim = self._data(fim, "Fim do período")
        lay.addWidget(self.inicio)
        lay.addWidget(rotulo("–", "legenda"))
        lay.addWidget(self.fim)
        self.equipamento.currentIndexChanged.connect(self._emitir)
        self.inicio.dateChanged.connect(self._emitir)
        self.fim.dateChanged.connect(self._emitir)

    def _data(self, valor: date | None, nome: str) -> QDateEdit:
        return campo_data(valor, nome)

    def valores(self) -> tuple[object, date, date]:
        return (self.equipamento.currentData(), self.inicio.date().toPython(), self.fim.date().toPython())

    def _emitir(self, *_):
        self.alterado.emit(*self.valores())


class SeletorPeriodo(QWidget):
    """[dd/mm/aaaa] – [dd/mm/aaaa]  [Todo o período]

    Emite `alterado(inicio: date, fim: date)` quando o usuário muda uma data
    e `tudo_solicitado()` no botão "Todo o período" (quem usa sabe qual é)."""

    alterado = Signal(object, object)
    tudo_solicitado = Signal()

    def __init__(self, inicio: date | None = None, fim: date | None = None, parent: QWidget | None = None):
        from .base import Botao

        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(ESPACO["sm"])
        self.inicio = campo_data(inicio, "Início do período")
        self.fim = campo_data(fim, "Fim do período")
        lay.addWidget(rotulo("Período", "rotulo_campo"))
        lay.addWidget(self.inicio)
        lay.addWidget(rotulo("–", "legenda"))
        lay.addWidget(self.fim)
        self.tudo = Botao("Todo o período", "fantasma", "calendar")
        self.tudo.setToolTip("Da primeira à última leitura do equipamento")
        lay.addWidget(self.tudo)
        self.inicio.dateChanged.connect(self._emitir)
        self.fim.dateChanged.connect(self._emitir)
        self.tudo.clicked.connect(self.tudo_solicitado)

    def definir(self, inicio: date, fim: date) -> None:
        """Muda as datas sem emitir `alterado`."""
        for campo, d in ((self.inicio, inicio), (self.fim, fim)):
            campo.blockSignals(True)
            campo.setDate(QDate(d.year, d.month, d.day))
            campo.blockSignals(False)

    def valores(self) -> tuple[date, date]:
        return (self.inicio.date().toPython(), self.fim.date().toPython())

    def _emitir(self, *_):
        self.alterado.emit(*self.valores())
