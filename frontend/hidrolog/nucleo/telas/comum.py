"""Peças comuns das páginas: página com recarga e aviso, formulário em diálogo,
formatação de tamanhos e grade de métricas."""

from __future__ import annotations

from datetime import date, datetime, time

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QFormLayout, QFrame, QGridLayout, QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget,
)

from design.componentes import Botao, FaixaAviso, Pagina, formatos, rotulo
from design.tema import DIMENSAO, ESPACO, repolir

from ..contexto import Contexto


class PaginaBase(Pagina):
    """Pagina do design + contexto, faixa de aviso e recarga sob demanda.

    `recarregar()` roda na primeira vez que a página aparece e de novo quando
    `ctx.dados_alterados` avisa um dos tipos de `depende_de` (se a página não
    está à vista, só na próxima vez que aparecer)."""

    depende_de: tuple[str, ...] = ()

    def __init__(self, ctx: Contexto, titulo: str, subtitulo: str = "", rolavel: bool = True,
                 embutida: bool = False):
        super().__init__(titulo, subtitulo, rolavel, embutida=embutida)
        self.ctx = ctx
        self.aviso = FaixaAviso(fechavel=True)
        self.corpo.addWidget(self.aviso)
        self._sujo = True
        ctx.dados_alterados.connect(self._ao_alterar)

    # chamado pelo shell (sinal pagina_alterada) sempre que a página é aberta
    def ao_mostrar(self) -> None:
        if self._sujo:
            self._sujo = False
            self.recarregar()

    def recarregar(self) -> None:
        """Busca os dados de novo no backend (sobrescrever)."""

    def visivel(self) -> bool:
        if self.embutida:
            return self.isVisible()
        shell = self.ctx.shell
        return shell is not None and shell.area.currentWidget() is self

    def _ao_alterar(self, tipo: str) -> None:
        if tipo in self.depende_de:
            if self.visivel():
                self.recarregar()
            else:
                self._sujo = True

    def mostrar_erro(self, erro: BaseException, contexto: str = "") -> str:
        texto = self.ctx.tratar_erro(erro, contexto or type(self).__name__)
        self.aviso.mostrar(texto, "erro")
        return texto

    def mostrar_aviso(self, texto: str, tom: str = "sucesso") -> None:
        self.aviso.mostrar(texto, tom)


def grade_metricas(cartoes: list[QWidget]) -> QGridLayout:
    grade = QGridLayout()
    grade.setSpacing(ESPACO["lg"])
    for i, c in enumerate(cartoes):
        grade.addWidget(c, 0, i)
        grade.setColumnStretch(i, 1)
    return grade


def tamanho_arquivo(n: int | None) -> str:
    """1536 -> '1,5 kB'; 2_500_000 -> '2,4 MB'."""
    if n is None:
        return formatos.TRACO
    for unidade, fator in (("GB", 1024 ** 3), ("MB", 1024 ** 2), ("kB", 1024)):
        if n >= fator:
            return formatos.numero(n / fator, 1, unidade)
    return formatos.inteiro(n, "bytes")


def inicio_do_dia(d: date | None) -> datetime | None:
    return datetime.combine(d, time.min) if d else None


def fim_do_dia(d: date | None) -> datetime | None:
    return datetime.combine(d, time(23, 59, 59)) if d else None


LARGURA_MIN_CAMPO = 300
LARGURA_COLUNA = 360        # largura mínima de cada coluna de um formulário em colunas


class DialogoFormulario(QDialog):
    """Formulário modal no padrão do design: título, explicação, faixa de erro,
    campos com rótulo alinhado e mensagem de erro logo abaixo de cada campo,
    botões Cancelar / <verbo>. Subclasses chamam `campo()` e implementam
    `validar()` (devolve True se pode salvar) e `salvar()` (chama o backend).

    Formulários longos podem ser divididos em colunas lado a lado com
    `colunas("Título 1", "Título 2")`, que devolve um QFormLayout por coluna
    (rótulo acima do campo); `campo()` usa o `self.form` atual. Os campos
    ficam numa área com rolagem que só aparece se o formulário não couber na
    tela: título, aviso e botões ficam sempre visíveis."""

    def __init__(self, titulo: str, descricao: str, texto_confirmar: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(titulo)
        self.setModal(True)
        self.setMinimumWidth(DIMENSAO["largura_formulario"] + 160)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(ESPACO["xl"], ESPACO["xl"], ESPACO["xl"], ESPACO["lg"])
        lay.setSpacing(ESPACO["md"])
        lay.addWidget(rotulo(titulo, "titulo"))
        if descricao:
            lay.addWidget(rotulo(descricao, "secundario", quebra=True))
        self.aviso = FaixaAviso()
        lay.addWidget(self.aviso)
        # campos numa área com rolagem (só aparece se não couber na tela)
        self._conteudo = QWidget()
        self._conteudo_lay = QVBoxLayout(self._conteudo)
        self._conteudo_lay.setContentsMargins(0, 0, ESPACO["xs"], 0)
        self._conteudo_lay.setSpacing(ESPACO["md"])
        self.form = self._novo_form()
        self._conteudo_lay.addLayout(self.form)
        self._area = QScrollArea()
        self._area.setFrameShape(QFrame.Shape.NoFrame)
        self._area.setWidgetResizable(True)
        self._area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._area.setWidget(self._conteudo)
        lay.addWidget(self._area, 1)
        lay.addSpacing(ESPACO["md"])
        botoes = QHBoxLayout()
        botoes.addStretch(1)
        self.botao_cancelar = Botao("Cancelar", "secundaria")
        self.botao_cancelar.clicked.connect(self.reject)
        self.botao_confirmar = Botao(texto_confirmar, "primaria")
        self.botao_confirmar.setDefault(True)
        self.botao_confirmar.clicked.connect(self._confirmar)
        botoes.addWidget(self.botao_cancelar)
        botoes.addWidget(self.botao_confirmar)
        lay.addLayout(botoes)
        self._erros: dict[QWidget, QLabel] = {}
        self.resultado = None
        # True: a ajuda de cada campo vira dica (ao passar o mouse), não texto embaixo
        self.ajuda_como_dica = False

    @staticmethod
    def _novo_form(empilhado: bool = False) -> QFormLayout:
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        form.setFormAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        form.setHorizontalSpacing(ESPACO["lg"])
        form.setVerticalSpacing(ESPACO["md"])
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        if empilhado:
            form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
            form.setVerticalSpacing(ESPACO["sm"])
        return form

    def colunas(self, *titulos: str) -> list[QFormLayout]:
        """Divide o formulário em colunas lado a lado, cada uma com um título
        (ou "" sem título) e o rótulo acima de cada campo. Devolve um
        QFormLayout por coluna; aponte `self.form` para a coluna antes de
        chamar `campo()`."""
        grade = QHBoxLayout()
        grade.setSpacing(ESPACO["xl"])
        forms = []
        for titulo in titulos:
            coluna = QVBoxLayout()
            coluna.setSpacing(ESPACO["md"])
            if titulo:
                coluna.addWidget(rotulo(titulo, "titulo_cartao"))
            form = self._novo_form(empilhado=True)
            coluna.addLayout(form)
            coluna.addStretch(1)
            grade.addLayout(coluna, 1)
            forms.append(form)
        self._conteudo_lay.addLayout(grade)
        self.setMinimumWidth(len(titulos) * LARGURA_COLUNA + (len(titulos) - 1) * ESPACO["xl"]
                             + 2 * ESPACO["xl"] + ESPACO["md"])
        return forms

    def showEvent(self, evento):
        # a área de campos cresce até o tamanho do conteúdo, limitada pela tela;
        # passando disso, aparece a rolagem e os botões continuam visíveis
        tela = self.screen().availableGeometry() if self.screen() else None
        limite = int(tela.height() * 0.9) if tela else 10_000
        resto = self.sizeHint().height() - self._area.sizeHint().height()
        conteudo = self._conteudo.sizeHint().height()
        self._area.setMinimumHeight(max(0, min(conteudo, limite - resto)))
        self.adjustSize()
        super().showEvent(evento)

    def campo(self, texto: str, widget: QWidget, ajuda: str = "") -> QWidget:
        """Acrescenta uma linha no `self.form` atual: rótulo à esquerda (ou acima,
        nas colunas) e o campo com ajuda e erro."""
        r = rotulo(texto, "rotulo_campo")
        if self.form.rowWrapPolicy() != QFormLayout.RowWrapPolicy.WrapAllRows:
            r.setFixedHeight(DIMENSAO["altura_controle"])
        r.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        bloco = QVBoxLayout()
        bloco.setSpacing(ESPACO["xs"])
        bloco.addWidget(widget)
        if ajuda and self.ajuda_como_dica:
            r.setToolTip(ajuda)
            widget.setToolTip(ajuda)
        elif ajuda:
            r_ajuda = rotulo(ajuda, "legenda", quebra=True)
            r_ajuda.ensurePolished()
            # o QFormLayout não reserva a altura do texto quebrado: garante as linhas na largura mínima
            empilhado = self.form.rowWrapPolicy() == QFormLayout.RowWrapPolicy.WrapAllRows
            r_ajuda.setMinimumHeight(r_ajuda.heightForWidth(LARGURA_COLUNA if empilhado else LARGURA_MIN_CAMPO))
            bloco.addWidget(r_ajuda)
        erro = rotulo("", "erro", quebra=True)
        erro.hide()
        bloco.addWidget(erro)
        self._erros[widget] = erro
        widget.setAccessibleName(texto)
        self.form.addRow(r, bloco)
        return widget

    def erro_campo(self, widget: QWidget, mensagem: str) -> None:
        widget.setProperty("invalido", "true")
        repolir(widget)
        self._erros[widget].setText(mensagem)
        self._erros[widget].show()

    def limpar_erros(self) -> None:
        self.aviso.limpar()
        for widget, erro in self._erros.items():
            widget.setProperty("invalido", "false")
            repolir(widget)
            erro.hide()

    def validar(self) -> bool:
        return True

    def salvar(self):
        raise NotImplementedError

    def tratar_erro_salvar(self, erro: BaseException) -> bool:
        """Mostra o erro do backend num campo (True) ou deixa para a faixa (False)."""
        return False

    def _confirmar(self) -> None:
        self.limpar_erros()
        if not self.validar():
            self.aviso.mostrar("Revise os campos destacados.", "erro")
            return
        try:
            self.resultado = self.salvar()
        except Exception as erro:  # noqa: BLE001
            ctx = getattr(self, "ctx", None)
            texto = ctx.tratar_erro(erro, type(self).__name__) if ctx else str(erro)
            if not self.tratar_erro_salvar(erro):
                self.aviso.mostrar(texto, "erro")
            else:
                self.aviso.mostrar("Revise os campos destacados.", "erro")
            return
        self.accept()
