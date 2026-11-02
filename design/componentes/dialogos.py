"""Diálogo de confirmação e faixa de aviso (mensagens inline)."""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtWidgets import QDialog, QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ..tema import ESPACO, gerenciador, pixmap_icone, repolir
from .base import Botao, rotulo

LARGURA_DIALOGO_SENHA = 620
LARGURA_ROTULO_DETALHE = 150

_ICONE_TOM = {
    "info": "info",
    "sucesso": "circle-check",
    "alerta": "triangle-alert",
    "erro": "circle-x",
    "neutro": "info",
}


class DialogoConfirmacao(QDialog):
    """Confirmação modal. Título em forma de pergunta, mensagem dizendo a
    consequência, botões com o verbo da ação (nunca "Sim/Não").

        if DialogoConfirmacao.perguntar(self, "Excluir equipamento?",
                "As 12.480 leituras do Pluviômetro 2 continuarão no banco, mas sem equipamento.",
                "Excluir", destrutivo=True):
            ...
    """

    def __init__(self, titulo: str, mensagem: str, texto_confirmar: str = "Confirmar",
                 texto_cancelar: str = "Cancelar", destrutivo: bool = False,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(titulo)
        self.setModal(True)
        self.setMinimumWidth(420)
        self.setMaximumWidth(520)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(ESPACO["xl"], ESPACO["xl"], ESPACO["xl"], ESPACO["lg"])
        lay.setSpacing(ESPACO["md"])

        topo = QHBoxLayout()
        topo.setSpacing(ESPACO["md"])
        self._icone = QLabel()
        self._icone.setPixmap(pixmap_icone("triangle-alert" if destrutivo else "info",
                                           "erro" if destrutivo else "primaria_texto", 20))
        topo.addWidget(self._icone, 0, Qt.AlignmentFlag.AlignTop)
        textos = QVBoxLayout()
        textos.setSpacing(ESPACO["xs"])
        textos.addWidget(rotulo(titulo, "subtitulo", quebra=True))
        textos.addWidget(rotulo(mensagem, "secundario", quebra=True))
        topo.addLayout(textos, 1)
        lay.addLayout(topo)
        lay.addSpacing(ESPACO["sm"])

        botoes = QHBoxLayout()
        botoes.addStretch(1)
        self.cancelar = Botao(texto_cancelar, "secundaria")
        self.confirmar = Botao(texto_confirmar, "perigo" if destrutivo else "primaria")
        self.cancelar.clicked.connect(self.reject)
        self.confirmar.clicked.connect(self.accept)
        botoes.addWidget(self.cancelar)
        botoes.addWidget(self.confirmar)
        lay.addLayout(botoes)
        # ação destrutiva: o foco inicial fica no Cancelar (Enter não apaga nada)
        (self.cancelar if destrutivo else self.confirmar).setDefault(True)
        (self.cancelar if destrutivo else self.confirmar).setFocus()

    @staticmethod
    def perguntar(parent: QWidget | None, titulo: str, mensagem: str, texto_confirmar: str = "Confirmar",
                  texto_cancelar: str = "Cancelar", destrutivo: bool = False) -> bool:
        d = DialogoConfirmacao(titulo, mensagem, texto_confirmar, texto_cancelar, destrutivo, parent)
        return d.exec() == QDialog.DialogCode.Accepted


class FaixaAviso(QFrame):
    """Mensagem inline (erro, alerta, sucesso, info) no topo de um formulário
    ou página. `fechavel=True` mostra um X. Fica oculta com texto vazio."""

    fechada = Signal()

    def __init__(self, texto: str = "", tom: str = "info", fechavel: bool = False,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.setProperty("papel", "faixa")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(ESPACO["md"], ESPACO["sm"], ESPACO["sm"], ESPACO["sm"])
        lay.setSpacing(ESPACO["sm"])
        # ícone, 1ª linha do texto e botão de fechar compartilham a mesma linha
        # de centro, no topo da faixa (vale para textos de uma ou várias linhas)
        self._icone = QLabel()
        self._icone.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self._icone, 0, Qt.AlignmentFlag.AlignTop)
        self.texto = rotulo("", None, quebra=True)
        self.texto.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.texto.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(self.texto, 1)
        self._fechar = None
        if fechavel:
            self._fechar = Botao("", "fantasma", "x")
            self._fechar.setFixedSize(24, 24)
            self._fechar.setToolTip("Fechar aviso")
            self._fechar.setAccessibleName("Fechar aviso")
            self._fechar.clicked.connect(self._ao_fechar)
            lay.addWidget(self._fechar, 0, Qt.AlignmentFlag.AlignTop)
        self._tom = tom
        self.mostrar(texto, tom)
        gerenciador().tema_alterado.connect(self._atualizar_icone)

    def mostrar(self, texto: str, tom: str | None = None) -> None:
        if tom:
            self._tom = tom
            self.setProperty("tom", tom)
            repolir(self)
            for filho in self.findChildren(QLabel):
                repolir(filho)
        self.texto.setText(texto)
        self.setVisible(bool(texto))
        self._atualizar_icone()

    def limpar(self) -> None:
        self.mostrar("")

    def _ao_fechar(self):
        self.hide()
        self.fechada.emit()

    def _atualizar_icone(self, *_):
        self._icone.setPixmap(pixmap_icone(_ICONE_TOM.get(self._tom, "info"), self._tom))
        self._alinhar_icone()

    def _alinhar_icone(self):
        # a fonte do texto só é definitiva depois que o tema (QSS) é aplicado
        linha = self.texto.fontMetrics().lineSpacing()
        altura = max(linha, self._fechar.height() if self._fechar else 0)
        recuo = (altura - linha) // 2
        self.texto.setContentsMargins(0, recuo, 0, 0)
        self._icone.setFixedHeight(altura)

    def showEvent(self, evento):
        self._alinhar_icone()
        super().showEvent(evento)

    def changeEvent(self, evento):
        if evento.type() in (QEvent.Type.StyleChange, QEvent.Type.FontChange):
            self._alinhar_icone()
        super().changeEvent(evento)


class DialogoSenha(QDialog):
    """Confirmação de ação sensível com a senha de quem está no computador.

        d = DialogoSenha("Instalar plugin “Pluviômetro” v0.1.0?",
                         [("Origem", "github.com/laboratorio/plugin-pluvio @ v0.1.0"), ("SHA-256", "3f9a…")],
                         aviso="Um plugin é um programa: …", texto_confirmar="Instalar",
                         ao_confirmar=lambda senha: servico.instalar_plugin(u, token, senha))
        d.exec()

    `ao_confirmar(senha)` faz a ação; se levantar uma exceção, o diálogo fica
    aberto e mostra `mensagem_erro(erro)` sob o campo (ex.: senha errada,
    tentativas restantes). Se a exceção tiver `encerrar = True`, o diálogo
    fecha (ex.: operação cancelada depois de 3 senhas erradas).
    `resultado` guarda o retorno de ao_confirmar.
    """

    def __init__(self, titulo: str, detalhes: list[tuple[str, str]] | None = None, mensagem: str = "",
                 aviso: str = "", texto_confirmar: str = "Confirmar", rotulo_senha: str = "Senha do master",
                 ao_confirmar=None, mensagem_erro=None, destrutivo: bool = False,
                 parent: QWidget | None = None):
        from PySide6.QtWidgets import QGridLayout, QLineEdit

        super().__init__(parent)
        self.setWindowTitle(titulo)
        self.setModal(True)
        self.setFixedWidth(LARGURA_DIALOGO_SENHA)
        self._ao_confirmar = ao_confirmar
        self._mensagem_erro = mensagem_erro or (lambda e: str(e))
        self.resultado = None
        self.erro_final: BaseException | None = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(ESPACO["xl"], ESPACO["xl"], ESPACO["xl"], ESPACO["lg"])
        lay.setSpacing(ESPACO["md"])
        lay.addWidget(rotulo(titulo, "subtitulo", quebra=True))
        if mensagem:
            lay.addWidget(rotulo(mensagem, "secundario", quebra=True))
        if detalhes:
            grade = QGridLayout()
            grade.setHorizontalSpacing(ESPACO["lg"])
            grade.setVerticalSpacing(ESPACO["sm"])
            largura_valor = LARGURA_DIALOGO_SENHA - 2 * ESPACO["xl"] - LARGURA_ROTULO_DETALHE - ESPACO["lg"]
            for i, (nome, valor) in enumerate(detalhes):
                r = rotulo(nome, "rotulo_campo")
                r.setFixedWidth(LARGURA_ROTULO_DETALHE)
                grade.addWidget(r, i, 0, Qt.AlignmentFlag.AlignTop)
                longo = " " not in valor and len(valor) > 40          # hash, caminho: quebra em qualquer ponto
                texto = "\u200b".join(valor[j:j + 16] for j in range(0, len(valor), 16)) if longo else valor
                v = rotulo(texto, None, mono=longo, quebra=True)
                v.setFixedWidth(largura_valor)
                v.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                grade.addWidget(v, i, 1, Qt.AlignmentFlag.AlignTop)
            lay.addLayout(grade)
        self.aviso = FaixaAviso(aviso, "alerta")
        lay.addWidget(self.aviso)
        lay.addWidget(rotulo(rotulo_senha, "rotulo_campo"))
        self.senha = QLineEdit()
        self.senha.setEchoMode(QLineEdit.EchoMode.Password)
        self.senha.setAccessibleName(rotulo_senha)
        lay.addWidget(self.senha)
        self.erro = rotulo("", "erro", quebra=True)
        self.erro.hide()
        lay.addWidget(self.erro)
        lay.addSpacing(ESPACO["sm"])
        botoes = QHBoxLayout()
        botoes.addStretch(1)
        self.cancelar = Botao("Cancelar", "secundaria")
        self.confirmar = Botao(texto_confirmar, "perigo" if destrutivo else "primaria")
        self.cancelar.clicked.connect(self.reject)
        self.confirmar.clicked.connect(self._confirmar)
        self.senha.returnPressed.connect(self._confirmar)
        botoes.addWidget(self.cancelar)
        botoes.addWidget(self.confirmar)
        lay.addLayout(botoes)
        self.senha.setFocus()

    def _confirmar(self) -> None:
        senha = self.senha.text()
        if not senha:
            self._mostrar_erro("Digite a senha para confirmar.")
            return
        try:
            self.resultado = self._ao_confirmar(senha) if self._ao_confirmar else senha
        except Exception as erro:  # noqa: BLE001 - a tela mostra a mensagem e decide se fecha
            self.senha.clear()
            if getattr(erro, "encerrar", False):
                self.erro_final = erro
                self.reject()
                return
            self._mostrar_erro(self._mensagem_erro(erro))
            return
        self.accept()

    def _mostrar_erro(self, texto: str) -> None:
        self.senha.setProperty("invalido", "true")
        repolir(self.senha)
        self.erro.setText(texto)
        self.erro.show()
