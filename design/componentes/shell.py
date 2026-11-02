"""
Janela principal: barra lateral com navegação por seções + cabeçalho com
o menu do usuário (Minha conta, Sair) + área de páginas.

Cada sensor (plugin) registra a própria seção e as próprias páginas; o shell
não conhece nenhum sensor:

    shell = JanelaPrincipal()
    shell.adicionar_secao("geral", "Geral", ordem=0, recolhivel=False)
    shell.adicionar_pagina("equipamentos", "Equipamentos", PaginaEquipamentos, "cpu", secao="geral")
    shell.adicionar_pagina("usuarios", "Usuários", PaginaUsuarios, "users", secao="admin",
                           perfis={"master"})
    # uma seção de outro módulo:
    shell.adicionar_secao("relatorios", "Relatórios", ordem=10)
    shell.adicionar_pagina("relatorios.mensal", "Mensal", fabrica, "chart-line", secao="relatorios")
    shell.definir_usuario("Ana Souza", "cadastro", "ana")
    # página fora da navegação, aberta pelo menu do usuário:
    shell.adicionar_pagina("conta", "Minha conta", fabrica, "user", na_navegacao=False)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QHBoxLayout, QMainWindow, QPushButton, QScrollArea,
    QSizePolicy, QStackedWidget, QVBoxLayout, QWidget,
)

from ..tema import DIMENSAO, ESPACO, alternar_tema, gerenciador, icone, modo_atual
from .base import Botao, Divisoria, rotulo
from ..tema.marca import marca_atual
from .usuario import MenuUsuario
from .vazio import EstadoVazio



@dataclass
class _Pagina:
    chave: str
    titulo: str
    fabrica: Callable[[], QWidget] | QWidget
    icone: str
    secao: str
    perfis: set[str] | None
    ordem: int
    migalha: str | None = None          # texto antes do título no cabeçalho (padrão: o da seção)
    na_navegacao: bool = True           # False: sem item na barra lateral (ex.: Minha conta)
    botao: QPushButton | None = None
    widget: QWidget | None = None


@dataclass
class _Secao:
    chave: str
    titulo: str
    ordem: int
    recolhivel: bool
    caixa: QWidget | None = None
    cabecalho: QPushButton | None = None
    itens: QVBoxLayout | None = None
    paginas: list = field(default_factory=list)
    aberta: bool = True


class BarraLateral(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("BarraLateral")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedWidth(DIMENSAO["largura_lateral"])
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # marca: laboratório pequeno acima do nome do app (marca tipográfica)
        m = marca_atual()
        marca = QWidget()
        marca.setFixedHeight(DIMENSAO["altura_cabecalho"] + ESPACO["lg"])
        lm = QVBoxLayout(marca)
        lm.setContentsMargins(ESPACO["xl"], ESPACO["md"], ESPACO["lg"], ESPACO["md"])
        lm.setSpacing(0)
        lm.addStretch(1)
        self.rotulo_laboratorio = rotulo((m.laboratorio or "").upper(), "marca_lab")
        self.rotulo_laboratorio.setToolTip(m.laboratorio_completo or "")
        self.rotulo_laboratorio.setVisible(bool(m.laboratorio))
        lm.addWidget(self.rotulo_laboratorio)
        self.rotulo_app = rotulo(m.nome_app, "marca_app")
        self.rotulo_app.setAccessibleName(m.titulo_janela)
        lm.addWidget(self.rotulo_app)
        lm.addStretch(1)
        lay.addWidget(marca)
        lay.addWidget(Divisoria())

        rolagem = QScrollArea()
        rolagem.setWidgetResizable(True)
        rolagem.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        rolagem.setFrameShape(QScrollArea.Shape.NoFrame)
        conteudo = QWidget()
        conteudo.setObjectName("ConteudoRolagem")
        self.secoes_layout = QVBoxLayout(conteudo)
        self.secoes_layout.setContentsMargins(ESPACO["md"], ESPACO["md"], ESPACO["md"], ESPACO["md"])
        self.secoes_layout.setSpacing(ESPACO["lg"])
        self.secoes_layout.addStretch(1)
        rolagem.setWidget(conteudo)
        lay.addWidget(rolagem, 1)

        lay.addWidget(Divisoria())
        rodape = QVBoxLayout()
        rodape.setContentsMargins(ESPACO["md"], ESPACO["sm"], ESPACO["md"], ESPACO["sm"])
        rodape.setSpacing(ESPACO["xs"])
        self.botao_tema = Botao("", "fantasma")
        self.botao_tema.setObjectName("ItemNav")
        rodape.addWidget(self.botao_tema)
        lay.addLayout(rodape)


class Cabecalho(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Cabecalho")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedHeight(DIMENSAO["altura_cabecalho"])
        lay = QHBoxLayout(self)
        lay.setContentsMargins(ESPACO["xl"], 0, ESPACO["lg"], 0)
        lay.setSpacing(ESPACO["sm"])
        self.secao = rotulo("", "secundario")
        self.separador = rotulo("/", "legenda")
        self.pagina = rotulo("", None)
        self.pagina.setStyleSheet("")  # peso vem do QSS do rótulo padrão
        lay.addWidget(self.secao)
        lay.addWidget(self.separador)
        lay.addWidget(self.pagina)
        lay.addStretch(1)
        self.contexto = QHBoxLayout()
        self.contexto.setSpacing(ESPACO["sm"])
        lay.addLayout(self.contexto)
        self._div_contexto = Divisoria(vertical=True)
        self._div_contexto.setFixedHeight(24)
        self._div_contexto.hide()
        lay.addWidget(self._div_contexto)
        self.ajuda = Botao("", "fantasma", "circle-help")
        self.ajuda.setToolTip("Central de ajuda")
        self.ajuda.setAccessibleName("Central de ajuda")
        lay.addWidget(self.ajuda)
        self.usuario = MenuUsuario()
        lay.addWidget(self.usuario)


class JanelaPrincipal(QMainWindow):
    """Shell do aplicativo. Ver docstring do módulo para o uso."""

    sair_solicitado = Signal()
    minha_conta_solicitada = Signal()
    ajuda_solicitada = Signal()
    pagina_alterada = Signal(str)
    tema_alterado = Signal(str)

    def __init__(self, titulo_janela: str | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(titulo_janela or marca_atual().titulo_janela)
        self.setMinimumSize(1100, 680)
        self._secoes: dict[str, _Secao] = {}
        self._paginas: dict[str, _Pagina] = {}
        self._perfil: str | None = None
        self._grupo = QButtonGroup(self)
        self._grupo.setExclusive(True)

        central = QWidget()
        central.setObjectName("Fundo")
        central.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        h = QHBoxLayout(central)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        self.lateral = BarraLateral()
        h.addWidget(self.lateral)
        coluna = QVBoxLayout()
        coluna.setContentsMargins(0, 0, 0, 0)
        coluna.setSpacing(0)
        self.cabecalho = Cabecalho()
        coluna.addWidget(self.cabecalho)
        self.area = QStackedWidget()
        self.area.setObjectName("AreaPaginas")
        coluna.addWidget(self.area, 1)
        h.addLayout(coluna, 1)
        self.setCentralWidget(central)

        self.cabecalho.usuario.sair_solicitado.connect(self.sair_solicitado)
        self.cabecalho.usuario.minha_conta_solicitada.connect(self.minha_conta_solicitada)
        self.cabecalho.ajuda.clicked.connect(self.ajuda_solicitada)
        self.lateral.botao_tema.clicked.connect(self._alternar_tema)
        gerenciador().tema_alterado.connect(self._atualizar_icones)
        self.adicionar_secao("geral", "Geral", ordem=0, recolhivel=False)
        self._atualizar_icones()

    # ------------------------------------------------------------------ API
    def adicionar_secao(self, chave: str, titulo: str, ordem: int = 100, recolhivel: bool = True) -> None:
        """Cria (ou renomeia) uma seção da navegação. Seções são ordenadas por
        `ordem`; sensores usam 10, 20, …; administração usa 900."""
        if chave in self._secoes:
            s = self._secoes[chave]
            s.titulo = titulo
            s.cabecalho.setText(titulo.upper())
            return
        s = _Secao(chave, titulo, ordem, recolhivel)
        s.caixa = QWidget()
        v = QVBoxLayout(s.caixa)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(ESPACO["xxs"])
        s.cabecalho = QPushButton(titulo.upper())
        s.cabecalho.setObjectName("CabecalhoSecao")
        s.cabecalho.setIconSize(QSize(14, 14))
        s.cabecalho.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        s.cabecalho.setCursor(Qt.CursorShape.PointingHandCursor if recolhivel else Qt.CursorShape.ArrowCursor)
        s.cabecalho.setFocusPolicy(Qt.FocusPolicy.StrongFocus if recolhivel else Qt.FocusPolicy.NoFocus)
        s.cabecalho.setAccessibleName(f"Seção {titulo}")
        if recolhivel:
            s.cabecalho.clicked.connect(lambda _=False, c=chave: self._recolher(c))
        v.addWidget(s.cabecalho)
        itens = QWidget()
        s.itens = QVBoxLayout(itens)
        s.itens.setContentsMargins(0, 0, 0, 0)
        s.itens.setSpacing(ESPACO["xxs"])
        v.addWidget(itens)
        self._secoes[chave] = s
        ordenadas = sorted(self._secoes.values(), key=lambda x: (x.ordem, x.titulo))
        lay = self.lateral.secoes_layout
        lay.insertWidget(ordenadas.index(s), s.caixa)
        self._atualizar_icones()

    def adicionar_pagina(self, chave: str, titulo: str, pagina: QWidget | Callable[[], QWidget],
                         nome_icone: str = "chevron-right", secao: str = "geral",
                         perfis: set[str] | None = None, ordem: int = 100, migalha: str | None = None,
                         na_navegacao: bool = True) -> None:
        """Registra uma página. `pagina` pode ser o widget ou uma fábrica
        (callable sem argumentos), criada só na primeira visita.
        `perfis`: quais perfis veem a página (None = todos).
        `na_navegacao=False`: sem item na barra lateral (abre por ir_para)."""
        if secao not in self._secoes:
            self.adicionar_secao(secao, secao.capitalize())
        p = _Pagina(chave, titulo, pagina, nome_icone, secao, set(perfis) if perfis else None, ordem, migalha,
                    na_navegacao)
        b = QPushButton(titulo)
        b.setObjectName("ItemNav")
        b.setCheckable(True)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setAccessibleName(titulo)
        b.clicked.connect(lambda _=False, c=chave: self.ir_para(c))
        p.botao = b
        self._grupo.addButton(b)
        s = self._secoes[secao]
        s.paginas.append(p)
        s.paginas.sort(key=lambda x: (x.ordem, x.titulo))
        s.itens.insertWidget(s.paginas.index(p), b)
        if isinstance(pagina, QWidget):
            p.widget = pagina
            self.area.addWidget(pagina)
        self._paginas[chave] = p
        self._aplicar_permissoes()
        self._atualizar_icones()
        if self.area.currentIndex() < 0 or len(self._paginas) == 1:
            pass

    def remover_pagina(self, chave: str) -> None:
        """Tira uma página da navegação (ex.: um equipamento que saiu dos Recentes)."""
        p = self._paginas.pop(chave, None)
        if p is None:
            return
        s = self._secoes[p.secao]
        s.paginas.remove(p)
        self._grupo.removeButton(p.botao)
        p.botao.hide()
        p.botao.setParent(None)
        p.botao.deleteLater()
        if p.widget is not None:
            if self.area.currentWidget() is p.widget:
                self.area.setCurrentIndex(0)
            self.area.removeWidget(p.widget)
            p.widget.deleteLater()
        self._aplicar_permissoes()

    def tem_pagina(self, chave: str) -> bool:
        return chave in self._paginas

    def ir_para(self, chave: str) -> QWidget | None:
        p = self._paginas.get(chave)
        if p is None or not self._permitido(p):
            return None
        if p.widget is None:
            p.widget = p.fabrica()
            self.area.addWidget(p.widget)
        self.area.setCurrentWidget(p.widget)
        p.botao.setChecked(True)
        s = self._secoes[p.secao]
        if not s.aberta:
            self._recolher(s.chave)
        self.cabecalho.secao.setText(p.migalha or s.titulo)
        self.cabecalho.pagina.setText(p.titulo)
        self.pagina_alterada.emit(chave)
        return p.widget

    def pagina(self, chave: str) -> QWidget | None:
        p = self._paginas.get(chave)
        return p.widget if p else None

    def definir_usuario(self, nome: str, perfil: str, login: str = "") -> None:
        """Mostra o usuário no cabeçalho e esconde o que o perfil não vê."""
        self._perfil = perfil
        self.cabecalho.usuario.definir_usuario(nome, perfil, login)
        self._aplicar_permissoes()
        atual = next((p for p in self._paginas.values() if p.widget is self.area.currentWidget()), None)
        if atual is None or not self._permitido(atual):
            primeira = next((p for s in sorted(self._secoes.values(), key=lambda x: x.ordem)
                             for p in s.paginas if self._permitido(p)), None)
            if primeira:
                self.ir_para(primeira.chave)

    @property
    def perfil(self) -> str | None:
        return self._perfil

    def adicionar_contexto(self, widget: QWidget) -> None:
        """Widget no cabeçalho, antes do usuário (ex.: seletor de equipamento)."""
        self.cabecalho.contexto.addWidget(widget)
        self.cabecalho._div_contexto.show()

    # ------------------------------------------------------------ internos
    def _permitido(self, p: _Pagina) -> bool:
        return p.perfis is None or (self._perfil in p.perfis)

    def _aplicar_permissoes(self):
        for s in self._secoes.values():
            visiveis = 0
            for p in s.paginas:
                ok = self._permitido(p) and p.na_navegacao
                p.botao.setVisible(ok and s.aberta)
                visiveis += ok
            s.caixa.setVisible(visiveis > 0)

    def _recolher(self, chave: str):
        s = self._secoes[chave]
        s.aberta = not s.aberta
        self._aplicar_permissoes()
        self._atualizar_icones()

    def _alternar_tema(self):
        novo = alternar_tema(QApplication.instance())
        self.tema_alterado.emit(novo)

    def _atualizar_icones(self, *_):
        for p in self._paginas.values():
            p.botao.setIcon(icone(p.icone, "texto_secundario", cor_ativo="primaria_texto"))
        for s in self._secoes.values():
            if s.recolhivel:
                s.cabecalho.setIcon(icone("chevron-down" if s.aberta else "chevron-right", "texto_terciario", 14))
            else:  # ícone transparente: mantém o texto alinhado com as seções recolhíveis
                s.cabecalho.setIcon(icone("chevron-down", "#00000000", 14))
        escuro = modo_atual() == "escuro"
        self.lateral.botao_tema.setText("Tema claro" if escuro else "Tema escuro")
        self.lateral.botao_tema.setIcon(icone("sun" if escuro else "moon", "texto_secundario"))


class PaginaNaoImplementada(EstadoVazio):
    """Marcador para páginas registradas mas ainda sem conteúdo."""

    def __init__(self, titulo: str = "Em construção", descricao: str = "Esta página ainda não foi implementada."):
        super().__init__(titulo, descricao, "layers")
