"""Peças pequenas usadas por todos os componentes e telas."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from ..tema import ESPACO, gerenciador, icone, repolir


def rotulo(texto: str = "", papel: str | None = None, mono: bool = False,
           quebra: bool = False, parent: QWidget | None = None) -> QLabel:
    """QLabel com papel tipográfico do tema: titulo_pagina, titulo, subtitulo,
    titulo_cartao, secundario, legenda, rotulo_campo, titulo_secao, erro."""
    r = QLabel(texto, parent)
    if papel:
        r.setProperty("papel", papel)
    if mono:
        r.setProperty("mono", "true")
    r.setWordWrap(quebra)
    r.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
    return r


class Botao(QPushButton):
    """QPushButton com variante do tema e ícone Lucide que acompanha o tema.

    variante: "primaria" | "secundaria" | "perigo" | "fantasma" | "link"
    """

    _COR_ICONE = {
        "primaria": "texto_sobre_primaria",
        "perigo": "superficie",
        "secundaria": "texto_secundario",
        "fantasma": "texto_secundario",
        "link": "primaria_texto",
    }

    def __init__(self, texto: str = "", variante: str = "secundaria", nome_icone: str | None = None,
                 grande: bool = False, parent: QWidget | None = None):
        # espaço fino entre ícone e texto (o Fusion cola os dois)
        super().__init__(f"\u2009{texto}" if (nome_icone and texto) else texto, parent)
        self.setAccessibleName(texto)
        self._nome_icone = nome_icone
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.definir_variante(variante)
        if grande:
            self.setProperty("grande", "true")
        gerenciador().tema_alterado.connect(self._atualizar_icone)

    def definir_variante(self, variante: str) -> None:
        self._variante = variante
        self.setProperty("variante", variante)
        repolir(self)
        self._atualizar_icone()

    def definir_icone(self, nome_icone: str | None) -> None:
        self._nome_icone = nome_icone
        self._atualizar_icone()

    def _atualizar_icone(self, *_):
        if self._nome_icone:
            self.setIcon(icone(self._nome_icone, self._COR_ICONE.get(self._variante, "texto_secundario")))
        else:
            self.setIcon(QIcon())


class Cartao(QFrame):
    """Superfície com borda e raio do tema. `self.corpo` é um QVBoxLayout."""

    def __init__(self, titulo: str | None = None, margem: int | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.setProperty("papel", "cartao")
        m = ESPACO["lg"] if margem is None else margem
        self.corpo = QVBoxLayout(self)
        self.corpo.setContentsMargins(m, m, m, m)
        self.corpo.setSpacing(ESPACO["md"])
        self.cabecalho: QHBoxLayout | None = None
        if titulo:
            self.cabecalho = QHBoxLayout()
            self.cabecalho.setSpacing(ESPACO["sm"])
            self.titulo = rotulo(titulo, "titulo_cartao")
            self.cabecalho.addWidget(self.titulo)
            self.cabecalho.addStretch(1)
            self.corpo.addLayout(self.cabecalho)


class Divisoria(QFrame):
    def __init__(self, vertical: bool = False, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("DivisoriaVertical" if vertical else "Divisoria")


class Pagina(QWidget):
    """Página de conteúdo padrão: título, subtítulo, área de ações à direita
    e corpo rolável. Use `self.corpo` (QVBoxLayout) para o conteúdo e
    `adicionar_acao(widget)` para botões do topo."""

    def __init__(self, titulo: str, subtitulo: str = "", rolavel: bool = True, parent: QWidget | None = None,
                 embutida: bool = False):
        """embutida=True: a página vai dentro de outra (ex. numa aba): sem
        margens, sem título e sem rolagem própria (quem a contém rola)."""
        super().__init__(parent)
        self.embutida = embutida
        if embutida:
            rolavel = False
        self.setObjectName("Fundo")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        externo = QVBoxLayout(self)
        externo.setContentsMargins(0, 0, 0, 0)
        externo.setSpacing(0)

        conteudo = QWidget()
        conteudo.setObjectName("ConteudoRolagem")
        self.corpo = QVBoxLayout(conteudo)
        m = 0 if embutida else ESPACO["xl"]
        self.corpo.setContentsMargins(m, m, m, m)
        self.corpo.setSpacing(ESPACO["lg"])

        topo = QHBoxLayout()
        topo.setSpacing(ESPACO["sm"])
        textos = QVBoxLayout()
        textos.setSpacing(ESPACO["xxs"])
        self.titulo = rotulo(titulo, "titulo_pagina")
        textos.addWidget(self.titulo)
        self.subtitulo = rotulo(subtitulo, "secundario", quebra=True)
        self.subtitulo.setVisible(bool(subtitulo))
        textos.addWidget(self.subtitulo)
        topo.addLayout(textos, 1)
        self._acoes = QHBoxLayout()
        self._acoes.setSpacing(ESPACO["sm"])
        topo.addLayout(self._acoes)
        topo.setAlignment(self._acoes, Qt.AlignmentFlag.AlignBottom)
        self.corpo.addLayout(topo)
        if embutida:
            self.titulo.hide()
            self.subtitulo.hide()
            self.subtitulo.setVisible = lambda *_: None      # o subtítulo fica no cabeçalho de quem contém

        if rolavel:
            area = QScrollArea()
            area.setWidgetResizable(True)
            area.setFrameShape(QFrame.Shape.NoFrame)
            area.setWidget(conteudo)
            externo.addWidget(area)
        else:
            externo.addWidget(conteudo)

    def adicionar_acao(self, widget: QWidget) -> None:
        self._acoes.addWidget(widget)


def expandir(widget: QWidget, h: bool = True, v: bool = False) -> QWidget:
    P = QSizePolicy.Policy
    widget.setSizePolicy(P.Expanding if h else P.Preferred, P.Expanding if v else P.Preferred)
    return widget
