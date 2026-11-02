"""Central de ajuda: busca, lista de tópicos (agrupados, só os do perfil) e o
texto do tópico (Markdown). Abre pelo botão "?" do cabeçalho."""

from __future__ import annotations

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import (
    QColor, QDesktopServices, QFont, QPalette, QTextBlockFormat, QTextCharFormat, QTextCursor, QTextDocument,
    QTextFormat,
)
from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QTextBrowser, QTreeWidget, QTreeWidgetItem, QVBoxLayout

from design.componentes import rotulo
from design.tema import ESPACO, FONTE, cor, fonte, fonte_mono, gerenciador

from ... import ajuda
from .comum import PaginaBase

LARGURA_LISTA = 260
CHAVE = Qt.ItemDataRole.UserRole
TAMANHO_TITULO = {1: FONTE["titulo_pagina"] + 2, 2: FONTE["titulo"], 3: FONTE["subtitulo"]}
ALTURA_LINHA = 145   # % da altura da fonte, no texto corrido


def formatar_documento(doc: QTextDocument) -> None:
    """Dá ao Markdown renderizado pelo Qt a tipografia do tema: títulos nos
    tamanhos do design, espaço entre parágrafos, linhas mais altas e blocos
    de código com fundo."""
    bloco = doc.begin()
    while bloco.isValid():
        fmt = QTextBlockFormat(bloco.blockFormat())
        cursor = QTextCursor(bloco)
        cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
        nivel = fmt.headingLevel()
        letra = QTextCharFormat()
        if nivel:
            fmt.setTopMargin(0 if bloco == doc.begin() else ESPACO["xl"] if nivel == 2 else ESPACO["lg"])
            fmt.setBottomMargin(ESPACO["md"] if nivel == 1 else ESPACO["sm"])
            letra.setFont(fonte(TAMANHO_TITULO.get(nivel, FONTE["corpo"]), FONTE["peso_semi"]))
            letra.setForeground(QColor(cor("texto")))
        elif fmt.hasProperty(QTextFormat.Property.BlockCodeFence) or fmt.nonBreakableLines():
            fmt.setBackground(QColor(cor("superficie_alt")))
            fmt.setLeftMargin(ESPACO["sm"])
            fmt.setRightMargin(ESPACO["sm"])
            fmt.setTopMargin(0)
            fmt.setBottomMargin(0)
            letra.setFont(fonte_mono(FONTE["pequeno"]))
        else:
            fmt.setLineHeight(ALTURA_LINHA, QTextBlockFormat.LineHeightTypes.ProportionalHeight.value)
            fmt.setBottomMargin(ESPACO["xs"] if bloco.textList() else ESPACO["md"])
        cursor.setBlockFormat(fmt)
        if letra.hasProperty(QTextFormat.Property.FontFamilies) or nivel:
            cursor.mergeCharFormat(letra)
        bloco = bloco.next()
    # o último bloco de cada trecho de código ganha o espaço de baixo
    bloco = doc.begin()
    while bloco.isValid():
        seguinte = bloco.next()
        if bloco.blockFormat().nonBreakableLines() and not (seguinte.isValid() and seguinte.blockFormat().nonBreakableLines()):
            fmt = QTextBlockFormat(bloco.blockFormat())
            fmt.setBottomMargin(ESPACO["md"])
            QTextCursor(bloco).setBlockFormat(fmt)
        bloco = seguinte


class PaginaAjuda(PaginaBase):
    def __init__(self, ctx):
        super().__init__(ctx, "Central de ajuda", "Como usar o Hidrolog, do primeiro acesso à administração.",
                         rolavel=False)
        self.perfil = ctx.usuario.perfil
        linha = QHBoxLayout()
        linha.setSpacing(ESPACO["lg"])

        coluna = QVBoxLayout()
        coluna.setSpacing(ESPACO["sm"])
        self.busca = QLineEdit()
        self.busca.setPlaceholderText("Buscar na ajuda…")
        self.busca.setClearButtonEnabled(True)
        self.busca.textChanged.connect(self._filtrar)
        coluna.addWidget(self.busca)
        self.lista = QTreeWidget()
        self.lista.setObjectName("ListaAjuda")
        self.lista.setHeaderHidden(True)
        self.lista.setRootIsDecorated(False)
        self.lista.setIndentation(ESPACO["md"])
        self.lista.setFixedWidth(LARGURA_LISTA)
        self.lista.currentItemChanged.connect(self._ao_escolher)
        coluna.addWidget(self.lista, 1)
        self.nada = rotulo("Nenhum tópico com esse termo.", "secundario", quebra=True)
        self.nada.hide()
        coluna.addWidget(self.nada)
        linha.addLayout(coluna)

        self.leitor = QTextBrowser()
        self.leitor.setProperty("papel", "leitor")
        self.leitor.setOpenLinks(False)
        self.leitor.anchorClicked.connect(self._abrir_link)
        self.leitor.document().setDocumentMargin(ESPACO["xl"])
        linha.addWidget(self.leitor, 1)
        self.corpo.addLayout(linha, 1)

        self.atual: str | None = None
        self._montar_lista(ajuda.topicos(self.perfil))
        gerenciador().tema_alterado.connect(self._tema_alterado)
        self._tema_alterado()
        self.abrir("boas-vindas")

    # ------------------------------------------------------------------ lista
    def _montar_lista(self, visiveis: list[ajuda.Topico]) -> None:
        chaves = {t.chave for t in visiveis}
        self.lista.blockSignals(True)
        self.lista.clear()
        for titulo, topicos in ajuda.agrupados(self.perfil):
            topicos = [t for t in topicos if t.chave in chaves]
            if not topicos:
                continue
            grupo = QTreeWidgetItem([titulo.upper()])
            grupo.setFlags(Qt.ItemFlag.ItemIsEnabled)
            f = QFont(fonte(FONTE["legenda"], FONTE["peso_semi"]))
            grupo.setFont(0, f)
            grupo.setForeground(0, QColor(cor("texto_terciario")))
            self.lista.addTopLevelItem(grupo)
            for t in topicos:
                item = QTreeWidgetItem([t.titulo])
                item.setData(0, CHAVE, t.chave)
                grupo.addChild(item)
        self.lista.expandAll()
        self.lista.blockSignals(False)
        self.nada.setVisible(not chaves)
        self._marcar(self.atual)

    def _itens(self):
        for i in range(self.lista.topLevelItemCount()):
            grupo = self.lista.topLevelItem(i)
            for j in range(grupo.childCount()):
                yield grupo.child(j)

    def topicos_listados(self) -> list[str]:
        return [item.data(0, CHAVE) for item in self._itens()]

    def _marcar(self, chave: str | None) -> None:
        self.lista.blockSignals(True)
        self.lista.setCurrentItem(next((i for i in self._itens() if i.data(0, CHAVE) == chave), None))
        self.lista.blockSignals(False)

    def _filtrar(self, termo: str) -> None:
        achados = ajuda.buscar(termo, self.perfil)
        self._montar_lista(achados)
        if achados and self.atual not in {t.chave for t in achados}:
            self.abrir(achados[0].chave)

    def _ao_escolher(self, item, _anterior) -> None:
        if item is not None and item.data(0, CHAVE):
            self.abrir(item.data(0, CHAVE))

    # ------------------------------------------------------------------ texto
    def abrir(self, chave: str) -> bool:
        """Mostra o tópico, se existir e o perfil puder ver."""
        topico = ajuda.TOPICO.get(chave)
        if topico is None or not topico.visivel_para(self.perfil):
            return False
        self.atual = chave
        self.leitor.setMarkdown(ajuda.texto(topico))
        formatar_documento(self.leitor.document())
        self.leitor.verticalScrollBar().setValue(0)
        self._marcar(chave)
        return True

    def _abrir_link(self, url: QUrl) -> None:
        if url.scheme() == ajuda.ESQUEMA_LINK:
            if not self.abrir(url.path()):
                self.mostrar_aviso("Este tópico é só para o perfil master.", "info")
        elif url.scheme() in ("http", "https"):
            QDesktopServices.openUrl(url)

    def _tema_alterado(self, *_) -> None:
        paleta = self.leitor.palette()
        paleta.setColor(QPalette.ColorRole.Link, QColor(cor("primaria_texto")))
        self.leitor.setPalette(paleta)
        self.leitor.document().setDefaultFont(fonte(FONTE["corpo"]))
        if self.atual:
            self.abrir(self.atual)            # links com a cor nova
        self._montar_lista([ajuda.TOPICO[c] for c in self.topicos_listados()] or ajuda.buscar(
            self.busca.text(), self.perfil))
