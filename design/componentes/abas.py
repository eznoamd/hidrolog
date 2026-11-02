"""Abas: barra de abas + área de conteúdo, com criação sob demanda.

    abas = Abas()
    abas.adicionar("visao", "Visão geral", lambda: MinhaAba(), "layout-dashboard")
    abas.adicionar_separador()                     # divide grupos (ex.: abas do plugin | abas comuns)
    abas.adicionar("cadastro", "Cadastro", PaginaCadastro(), "pencil")
    abas.aba_alterada.connect(lambda chave: ...)
    abas.ir_para("cadastro")

O widget de cada aba pode ser passado pronto ou como fábrica (callable sem
argumentos), chamada só na primeira vez que a aba é aberta.
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QStackedWidget, QTabBar, QVBoxLayout, QWidget

from ..tema import ESPACO, gerenciador, icone


class Abas(QWidget):
    aba_alterada = Signal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(ESPACO["lg"])
        self.barra = QTabBar()
        self.barra.setObjectName("Abas")
        self.barra.setExpanding(False)
        self.barra.setDrawBase(False)
        self.barra.setUsesScrollButtons(True)
        self.barra.setDocumentMode(True)
        lay.addWidget(self.barra)
        self.area = QStackedWidget()
        lay.addWidget(self.area, 1)
        self._chaves: list[str | None] = []          # None = separador
        self._fabricas: dict[str, Callable[[], QWidget] | QWidget] = {}
        self._widgets: dict[str, QWidget] = {}
        self._icones: dict[str, str | None] = {}
        self.barra.currentChanged.connect(self._ao_mudar)
        gerenciador().tema_alterado.connect(self._atualizar_icones)

    # ------------------------------------------------------------------ API
    def adicionar(self, chave: str, titulo: str, widget: QWidget | Callable[[], QWidget],
                  nome_icone: str | None = None, dica: str | None = None) -> None:
        if chave in self._fabricas:
            raise ValueError(f"aba repetida: {chave}")
        self._fabricas[chave] = widget
        self._icones[chave] = nome_icone
        i = self.barra.addTab(titulo)
        self.barra.setTabData(i, chave)
        if dica:
            self.barra.setTabToolTip(i, dica)
        self._chaves.append(chave)
        if isinstance(widget, QWidget):
            self._widgets[chave] = widget
            self.area.addWidget(widget)
        self._atualizar_icones()
        if len([c for c in self._chaves if c]) == 1:
            self._ao_mudar(i)

    def adicionar_separador(self) -> None:
        """Divisória entre grupos de abas (não clicável)."""
        i = self.barra.addTab("│")
        self.barra.setTabEnabled(i, False)
        self.barra.setTabData(i, None)
        self.barra.setTabToolTip(i, "")
        self._chaves.append(None)

    def chaves(self) -> list[str]:
        return [c for c in self._chaves if c]

    def titulos(self) -> list[str]:
        return [self.barra.tabText(i) for i, c in enumerate(self._chaves) if c]

    def atual(self) -> str | None:
        i = self.barra.currentIndex()
        return self._chaves[i] if 0 <= i < len(self._chaves) else None

    def widget(self, chave: str) -> QWidget | None:
        return self._widgets.get(chave)

    def ir_para(self, chave: str) -> QWidget | None:
        if chave not in self._fabricas:
            return None
        i = self._chaves.index(chave)
        if self.barra.currentIndex() != i:
            self.barra.setCurrentIndex(i)
        else:
            self._ao_mudar(i)
        return self._widgets.get(chave)

    # ------------------------------------------------------------ internos
    def _criar(self, chave: str) -> QWidget:
        if chave not in self._widgets:
            w = self._fabricas[chave]()
            self._widgets[chave] = w
            self.area.addWidget(w)
        return self._widgets[chave]

    def _ao_mudar(self, i: int) -> None:
        if not (0 <= i < len(self._chaves)) or self._chaves[i] is None:
            return
        chave = self._chaves[i]
        self.area.setCurrentWidget(self._criar(chave))
        self.aba_alterada.emit(chave)

    def _atualizar_icones(self, *_):
        for i, chave in enumerate(self._chaves):
            nome = self._icones.get(chave) if chave else None
            if nome:
                self.barra.setTabIcon(i, icone(nome, "texto_secundario", cor_ativo="primaria_texto"))
