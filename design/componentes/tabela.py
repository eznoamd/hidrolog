"""Tabela densa com busca, filtros por coluna, ordenação e estado vazio."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Callable

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QRectF, QSortFilterProxyModel, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QHBoxLayout, QHeaderView, QLineEdit, QStackedWidget,
    QStyle, QStyledItemDelegate, QStyleOptionViewItem, QTableView, QVBoxLayout, QWidget,
)

from ..tema import DIMENSAO, ESPACO, FONTE, RAIO, cor, fonte, fonte_mono, gerenciador, icone
from . import formatos
from .base import rotulo
from .vazio import EstadoVazio

PAPEL_BRUTO = Qt.ItemDataRole.UserRole + 1
PAPEL_LINHA = Qt.ItemDataRole.UserRole + 2

TIPOS_NUMERICOS = ("numero", "inteiro")
TIPOS_MONO = ("numero", "inteiro", "data", "data_hora", "mono")


@dataclass
class Coluna:
    """Definição de uma coluna.

    tipo: "texto" | "numero" | "inteiro" | "data" | "data_hora" | "mono" | "selo"
    unidade: aparece no cabeçalho, ex.: "Chuva (mm)".
    selo: para tipo "selo", função valor -> (texto, tom[, solido]).
    formatar: função valor -> str, para casos especiais.
    dica: texto do tooltip do cabeçalho (use com títulos abreviados).
    """

    chave: str
    titulo: str
    tipo: str = "texto"
    unidade: str | None = None
    casas: int = 1
    largura: int | None = None
    estica: bool = False
    selo: Callable[[Any], tuple] | None = None
    formatar: Callable[[Any], str] | None = None
    dica: str | None = None          # dica do cabeçalho (útil com título abreviado)

    @property
    def cabecalho(self) -> str:
        return f"{self.titulo} ({self.unidade})" if self.unidade else self.titulo

    def texto(self, valor) -> str:
        if self.formatar:
            return self.formatar(valor)
        if self.tipo == "numero":
            return formatos.numero(valor, self.casas)
        if self.tipo == "inteiro":
            return formatos.inteiro(valor)
        if self.tipo == "data":
            return formatos.data(valor)
        if self.tipo == "data_hora":
            return formatos.data_hora(valor)
        if self.tipo == "selo" and self.selo and valor is not None:
            return str(self.selo(valor)[0])
        return formatos.TRACO if valor in (None, "") else str(valor)


def _sem_acento(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto.casefold()) if unicodedata.category(c) != "Mn")


class _Modelo(QAbstractTableModel):
    def __init__(self, colunas: list[Coluna]):
        super().__init__()
        self.colunas = colunas
        self.linhas: list[dict] = []

    def definir(self, linhas: list[dict]):
        self.beginResetModel()
        self.linhas = list(linhas)
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.linhas)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.colunas)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        col = self.colunas[index.column()]
        linha = self.linhas[index.row()]
        valor = linha.get(col.chave)
        if role == Qt.ItemDataRole.DisplayRole:
            return col.texto(valor)
        if role == PAPEL_BRUTO:
            if isinstance(valor, (datetime, date)):
                return valor.isoformat()
            return valor if valor is not None else ""
        if role == PAPEL_LINHA:
            return linha
        if role == Qt.ItemDataRole.TextAlignmentRole:
            h = Qt.AlignmentFlag.AlignRight if col.tipo in TIPOS_NUMERICOS else Qt.AlignmentFlag.AlignLeft
            return int(h | Qt.AlignmentFlag.AlignVCenter)
        if role == Qt.ItemDataRole.FontRole:
            return fonte_mono(FONTE["pequeno"]) if col.tipo in TIPOS_MONO else None
        if role == Qt.ItemDataRole.ForegroundRole and valor in (None, ""):
            return QColor(cor("texto_terciario"))
        if role == Qt.ItemDataRole.ToolTipRole and col.tipo in ("texto", "mono") and valor:
            return str(valor)
        return None

    def headerData(self, secao, orientacao, role=Qt.ItemDataRole.DisplayRole):
        if orientacao != Qt.Orientation.Horizontal:
            return None
        col = self.colunas[secao]
        if role == Qt.ItemDataRole.DisplayRole:
            return col.cabecalho
        if role == Qt.ItemDataRole.ToolTipRole:
            return col.dica
        if role == Qt.ItemDataRole.TextAlignmentRole:
            h = Qt.AlignmentFlag.AlignRight if col.tipo in TIPOS_NUMERICOS else Qt.AlignmentFlag.AlignLeft
            return int(h | Qt.AlignmentFlag.AlignVCenter)
        return None


class _Filtro(QSortFilterProxyModel):
    def __init__(self):
        super().__init__()
        self.busca = ""
        self.por_coluna: dict[int, str] = {}
        self.setSortRole(PAPEL_BRUTO)

    def filterAcceptsRow(self, linha, pai):
        m = self.sourceModel()
        for col, alvo in self.por_coluna.items():
            if alvo and m.data(m.index(linha, col, pai)) != alvo:
                return False
        if not self.busca:
            return True
        return any(self.busca in _sem_acento(str(m.data(m.index(linha, c, pai)) or ""))
                   for c in range(m.columnCount()))

    def lessThan(self, a, b):
        va, vb = a.data(PAPEL_BRUTO), b.data(PAPEL_BRUTO)
        try:
            return va < vb
        except TypeError:
            return str(va) < str(vb)


class _DelegadoSelo(QStyledItemDelegate):
    """Desenha a célula do tipo "selo" como pílula, com as cores do tema."""

    def __init__(self, coluna: Coluna, parent=None):
        super().__init__(parent)
        self.coluna = coluna

    def paint(self, painter: QPainter, opcao: QStyleOptionViewItem, index):
        estilo = QStyleOptionViewItem(opcao)
        self.initStyleOption(estilo, index)
        estilo.text = ""
        w = estilo.widget
        (w.style() if w else QStyle).drawControl(QStyle.ControlElement.CE_ItemViewItem, estilo, painter, w)
        bruto = index.data(PAPEL_LINHA).get(self.coluna.chave)
        if bruto is None or not self.coluna.selo:
            return
        info = self.coluna.selo(bruto)
        texto, tom = info[0], info[1]
        solido = len(info) > 2 and info[2]
        f = fonte(FONTE["pequeno"], FONTE["peso_semi"])
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setFont(f)
        largura = painter.fontMetrics().horizontalAdvance(texto) + 2 * ESPACO["sm"]
        altura = DIMENSAO["altura_selo"]
        r = opcao.rect
        caixa = QRectF(r.left() + ESPACO["sm"], r.center().y() - altura / 2 + 0.5, largura, altura)
        fundo = cor(tom if solido else f"{tom}_suave")
        frente = cor("superficie" if solido else tom)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(fundo))
        painter.drawRoundedRect(caixa, RAIO["pilula"], RAIO["pilula"])
        painter.setPen(QPen(QColor(frente)))
        painter.drawText(caixa, Qt.AlignmentFlag.AlignCenter, texto)
        painter.restore()


class TabelaFiltravel(QWidget):
    """Tabela com campo de busca (sem acento/maiúsculas), filtros de coluna
    opcionais, contagem de registros, ordenação por clique e estado vazio.

        t = TabelaFiltravel([Coluna("nome", "Nome", estica=True),
                             Coluna("chuva", "Chuva", "numero", unidade="mm")])
        t.definir_linhas([{"nome": "Evento 1", "chuva": 12.3}])
        t.linha_ativada.connect(lambda linha: ...)
    """

    linha_ativada = Signal(dict)
    selecao_alterada = Signal(list)

    def __init__(self, colunas: list[Coluna], texto_busca: str = "Buscar…",
                 titulo_vazio: str = "Nenhum registro", descricao_vazio: str = "",
                 icone_vazio: str = "inbox", ordenar_por: str | None = None,
                 decrescente: bool = False, mostrar_busca: bool = True, embutida: bool = False,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.colunas = colunas
        self._modelo = _Modelo(colunas)
        self._filtro = _Filtro()
        self._filtro.setSourceModel(self._modelo)
        self._combos: dict[int, QComboBox] = {}

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(ESPACO["sm"])

        self.barra = QHBoxLayout()
        self.barra.setSpacing(ESPACO["sm"])
        self.busca = QLineEdit()
        self.busca.setPlaceholderText(texto_busca)
        self.busca.setClearButtonEnabled(True)
        self.busca.setProperty("busca", "true")
        self.busca.setFixedWidth(280)
        self.busca.setAccessibleName("Buscar na tabela")
        self._acao_busca = self.busca.addAction(icone("search", "texto_terciario"), QLineEdit.ActionPosition.LeadingPosition)
        self.busca.textChanged.connect(self._ao_buscar)
        self.busca.setVisible(mostrar_busca)
        self.barra.addWidget(self.busca)
        self._pos_filtros = self.barra.count()
        self.barra.addStretch(1)
        self.contagem = rotulo("", "legenda")
        self.barra.addWidget(self.contagem)
        self._pos_acoes = self.barra.count()
        lay.addLayout(self.barra)

        self.tabela = QTableView()
        self.tabela.setModel(self._filtro)
        if embutida:  # dentro de um Cartao: sem borda própria
            self.tabela.setProperty("embutida", "true")
        self.tabela.setSortingEnabled(True)
        self.tabela.setAlternatingRowColors(True)
        self.tabela.setShowGrid(False)
        self.tabela.setWordWrap(False)
        self.tabela.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabela.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tabela.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabela.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.tabela.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.tabela.verticalHeader().hide()
        self.tabela.verticalHeader().setDefaultSectionSize(DIMENSAO["altura_linha_tabela"])
        self.tabela.verticalHeader().setMinimumSectionSize(DIMENSAO["altura_linha_tabela"])
        cab = self.tabela.horizontalHeader()
        cab.setHighlightSections(False)
        cab.setSectionsClickable(True)
        cab.setStretchLastSection(False)
        cab.setMinimumSectionSize(60)
        cab.setFixedHeight(DIMENSAO["altura_linha_tabela"] + 2)
        for i, col in enumerate(colunas):
            if col.tipo == "selo":
                self.tabela.setItemDelegateForColumn(i, _DelegadoSelo(col, self.tabela))
            if col.estica:
                cab.setSectionResizeMode(i, QHeaderView.ResizeMode.Stretch)
            elif col.tipo in TIPOS_MONO:  # números e datas nunca cortados
                cab.setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)
            elif col.largura:
                cab.setSectionResizeMode(i, QHeaderView.ResizeMode.Interactive)
                self.tabela.setColumnWidth(i, col.largura)
            else:
                cab.setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)
        self.tabela.doubleClicked.connect(self._ao_ativar)
        self.tabela.activated.connect(self._ao_ativar)
        self.tabela.selectionModel().selectionChanged.connect(lambda *_: self.selecao_alterada.emit(self.selecao()))

        self._texto_vazio = (titulo_vazio, descricao_vazio)
        self.vazio = EstadoVazio(titulo_vazio, descricao_vazio, icone_vazio)
        self._pilha = QStackedWidget()
        self._pilha.addWidget(self.tabela)
        self._pilha.addWidget(self.vazio)
        lay.addWidget(self._pilha, 1)

        if ordenar_por:
            idx = next(i for i, c in enumerate(colunas) if c.chave == ordenar_por)
            self.tabela.sortByColumn(idx, Qt.SortOrder.DescendingOrder if decrescente else Qt.SortOrder.AscendingOrder)
        else:
            self.tabela.sortByColumn(-1, Qt.SortOrder.AscendingOrder)
        gerenciador().tema_alterado.connect(self._ao_mudar_tema)
        self._atualizar_contagem()

    # ---- API ----
    def definir_linhas(self, linhas: list[dict]) -> None:
        self._modelo.definir(linhas)
        for idx, combo in self._combos.items():
            atual = combo.currentText()
            valores = sorted({self._modelo.data(self._modelo.index(r, idx)) for r in range(self._modelo.rowCount())})
            combo.blockSignals(True)
            combo.clear()
            combo.addItem(combo.property("todos"))
            combo.addItems([v for v in valores if v])
            combo.setCurrentText(atual)
            combo.blockSignals(False)
        self._atualizar_contagem()

    def adicionar_filtro(self, chave: str, texto_todos: str = "Todos") -> QComboBox:
        """Combo de filtro por valor exato de uma coluna (ex.: tipo, perfil)."""
        idx = next(i for i, c in enumerate(self.colunas) if c.chave == chave)
        combo = QComboBox()
        combo.setProperty("todos", texto_todos)
        combo.addItem(texto_todos)
        combo.setMinimumWidth(160)
        combo.setAccessibleName(f"Filtrar por {self.colunas[idx].titulo}")
        combo.currentIndexChanged.connect(lambda _=None, i=idx, c=combo: self._ao_filtrar_coluna(i, c))
        self.barra.insertWidget(self._pos_filtros, combo)
        self._pos_filtros += 1
        self._pos_acoes += 1
        self._combos[idx] = combo
        self.definir_linhas(self._modelo.linhas)
        return combo

    def adicionar_acao(self, widget: QWidget) -> None:
        """Botão na barra, à direita da contagem."""
        self.barra.addWidget(widget)

    def selecao(self) -> list[dict]:
        linhas = {self._filtro.mapToSource(i).row() for i in self.tabela.selectionModel().selectedRows()}
        return [self._modelo.linhas[r] for r in sorted(linhas)]

    def linhas(self) -> list[dict]:
        return list(self._modelo.linhas)

    def definir_vazio(self, titulo: str, descricao: str = "") -> None:
        """Texto mostrado quando a tabela não tem nenhuma linha."""
        self._texto_vazio = (titulo, descricao)
        self._atualizar_contagem()

    # ---- internos ----
    def _ao_buscar(self, texto: str):
        self._filtro.busca = _sem_acento(texto.strip())
        self._filtro.invalidateFilter()
        self._atualizar_contagem()

    def _ao_filtrar_coluna(self, idx: int, combo: QComboBox):
        self._filtro.por_coluna[idx] = "" if combo.currentIndex() <= 0 else combo.currentText()
        self._filtro.invalidateFilter()
        self._atualizar_contagem()

    def _ao_ativar(self, index):
        self.linha_ativada.emit(self._filtro.data(index, PAPEL_LINHA))

    def _atualizar_contagem(self):
        total, visiveis = self._modelo.rowCount(), self._filtro.rowCount()
        palavra = "registro" if total == 1 else "registros"
        filtrando = bool(self._filtro.busca) or any(self._filtro.por_coluna.values())
        self.contagem.setText(f"{visiveis} de {total} {palavra}" if filtrando else f"{total} {palavra}")
        titulo, descricao = self._texto_vazio if total == 0 else (
            "Nada encontrado", "Nenhum registro corresponde à busca ou aos filtros.")
        self.vazio.titulo.setText(titulo)
        self.vazio.descricao.setText(descricao)
        self.vazio.descricao.setVisible(bool(descricao))
        self._pilha.setCurrentIndex(1 if visiveis == 0 else 0)

    def _ao_mudar_tema(self, *_):
        self.busca.removeAction(self._acao_busca)
        self._acao_busca = self.busca.addAction(icone("search", "texto_terciario"), QLineEdit.ActionPosition.LeadingPosition)
        self.tabela.viewport().update()
