"""Área de soltar arquivo/pasta para a importação de dados."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPainter, QPen, QColor
from PySide6.QtWidgets import QDialog, QFileDialog, QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ..tema import DIMENSAO, ESPACO, RAIO, cor, gerenciador, pixmap_icone
from .base import Botao, rotulo


class DialogoArquivoOuPasta(QFileDialog):
    """Diálogo único para escolher um arquivo OU uma pasta (o diálogo nativo
    só faz um dos dois). "Escolher" com um arquivo selecionado devolve o
    arquivo; com uma pasta selecionada, ou dentro de uma pasta sem nada
    selecionado, devolve a pasta. Duplo clique numa pasta entra nela.

        caminho = DialogoArquivoOuPasta.escolher(parent, (".zip", ".rar"))
    """

    def __init__(self, parent: QWidget | None, extensoes: tuple[str, ...], aceita_pasta: bool = True,
                 titulo: str = "Escolher pasta ou arquivo de dados", rotulo_filtro: str | None = None):
        super().__init__(parent, titulo)
        self.aceita_pasta = aceita_pasta
        self.escolhido: str | None = None
        self.setOption(QFileDialog.Option.DontUseNativeDialog, True)
        # no diálogo do Qt (não nativo), o modo "pasta" também mostra os arquivos e
        # deixa "Escolher" ativo para a pasta atual; selecionar um arquivo o escolhe
        self.setFileMode(QFileDialog.FileMode.Directory if aceita_pasta else QFileDialog.FileMode.ExistingFile)
        self.setOption(QFileDialog.Option.ShowDirsOnly, False)
        padroes = " ".join(f"*{e}" for e in extensoes)
        rotulo_filtro = rotulo_filtro or ("Pastas e arquivos de dados" if aceita_pasta else "Arquivos de dados")
        self.setNameFilters([f"{rotulo_filtro} ({padroes})", "Todos os arquivos (*)"])
        for rotulo_dialogo, texto in ((QFileDialog.DialogLabel.Accept, "Escolher"),
                                      (QFileDialog.DialogLabel.Reject, "Cancelar"),
                                      (QFileDialog.DialogLabel.LookIn, "Procurar em:"),
                                      (QFileDialog.DialogLabel.FileName, "Pasta ou arquivo:"),
                                      (QFileDialog.DialogLabel.FileType, "Mostrar:")):
            self.setLabelText(rotulo_dialogo, texto)

    def accept(self) -> None:
        selecionados = self.selectedFiles()
        caminho = Path(selecionados[0]) if selecionados else Path(self.directory().absolutePath())
        if caminho.is_dir():
            if not self.aceita_pasta:
                self.setDirectory(str(caminho))       # sem pasta: entra nela, como o diálogo comum
                return
            self.escolhido = str(caminho)
            QDialog.accept(self)
            return
        if caminho.is_file():
            self.escolhido = str(caminho)
            QDialog.accept(self)

    @classmethod
    def escolher(cls, parent: QWidget | None, extensoes: tuple[str, ...], aceita_pasta: bool = True,
                 **opcoes) -> str | None:
        dialogo = cls(parent, extensoes, aceita_pasta, **opcoes)
        return dialogo.escolhido if dialogo.exec() == QDialog.DialogCode.Accepted else None


class AreaSoltarArquivo(QFrame):
    """Arraste aqui uma pasta, .zip ou .rar (ou use o botão "Escolher…", que
    aceita os dois).

    Emite `caminho_escolhido(str)` com um caminho válido e
    `caminho_rejeitado(str, motivo)` quando o item não é aceito.
    """

    caminho_escolhido = Signal(str)
    caminho_rejeitado = Signal(str, str)

    def __init__(self, extensoes: tuple[str, ...] = (".zip", ".rar"), aceita_pasta: bool = True,
                 titulo: str = "Arraste a pasta do cartão SD ou um arquivo .zip/.rar",
                 descricao: str = "Também aceita a pasta de uma única medição.",
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.extensoes = tuple(e.lower() for e in extensoes)
        self.aceita_pasta = aceita_pasta
        self._estado = "normal"  # normal | arrastando | invalido
        self.caminho: str | None = None
        self.setAcceptDrops(True)
        self.setMinimumHeight(176)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAccessibleName("Área para soltar pasta ou arquivo de dados")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(ESPACO["xl"], ESPACO["xl"], ESPACO["xl"], ESPACO["xl"])
        lay.setSpacing(ESPACO["sm"])
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._icone = QLabel()
        self._icone.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self._icone)
        self.titulo = rotulo(titulo, "titulo_cartao")
        self.titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.titulo)
        self.descricao = rotulo(descricao, "legenda")
        self.descricao.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.descricao)
        lay.addSpacing(ESPACO["xs"])
        botoes = QHBoxLayout()
        botoes.setSpacing(ESPACO["sm"])
        botoes.addStretch(1)
        self.botao_escolher = Botao("Escolher…", "secundaria", "folder-open")
        self.botao_escolher.setToolTip("Escolha a pasta do cartão SD, a pasta de uma medição ou um arquivo "
                                       + "/".join(self.extensoes))
        self.botao_escolher.clicked.connect(self._escolher)
        botoes.addWidget(self.botao_escolher)
        botoes.addStretch(1)
        lay.addLayout(botoes)
        self.selecionado = rotulo("", "legenda", mono=True)
        self.selecionado.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.selecionado.hide()
        lay.addWidget(self.selecionado)

        self._atualizar_icone()
        gerenciador().tema_alterado.connect(self._atualizar_icone)

    # ---- validação ----
    def validar(self, caminho: str) -> str | None:
        """None se aceito; senão o motivo (texto para o usuário)."""
        p = Path(caminho)
        if p.is_dir():
            return None if self.aceita_pasta else "Pastas não são aceitas aqui."
        if p.suffix.lower() in self.extensoes:
            return None if p.exists() else "O arquivo não foi encontrado."
        aceitos = ", ".join(self.extensoes)
        return f"“{p.name}” não é aceito. Use uma pasta ou um arquivo {aceitos}."

    def definir_caminho(self, caminho: str) -> bool:
        motivo = self.validar(caminho)
        if motivo:
            self._estado = "invalido"
            self.selecionado.setText(motivo)
            self.selecionado.setProperty("papel", "erro")
            self.caminho_rejeitado.emit(caminho, motivo)
        else:
            self._estado = "normal"
            self.caminho = caminho
            self.selecionado.setText(caminho)
            self.selecionado.setProperty("papel", "legenda")
            self.caminho_escolhido.emit(caminho)
        self.selecionado.style().unpolish(self.selecionado)
        self.selecionado.style().polish(self.selecionado)
        self.selecionado.show()
        self._atualizar_icone()
        self.update()
        return motivo is None

    # ---- arrastar e soltar ----
    def dragEnterEvent(self, ev):
        urls = ev.mimeData().urls()
        if len(urls) == 1 and urls[0].isLocalFile():
            self._estado = "arrastando" if self.validar(urls[0].toLocalFile()) is None else "invalido"
            ev.acceptProposedAction()
            self._atualizar_icone()
            self.update()
        else:
            ev.ignore()

    def dragLeaveEvent(self, ev):
        self._estado = "normal"
        self._atualizar_icone()
        self.update()

    def dropEvent(self, ev):
        urls = ev.mimeData().urls()
        self._estado = "normal"
        if urls:
            self.definir_caminho(urls[0].toLocalFile())
        ev.acceptProposedAction()

    def _escolher(self):
        caminho = DialogoArquivoOuPasta.escolher(self, self.extensoes, self.aceita_pasta)
        if caminho:
            self.definir_caminho(caminho)

    # ---- desenho: borda tracejada, sem sombra ----
    def _atualizar_icone(self, *_):
        nome, tom = {"arrastando": ("download", "primaria_texto"), "invalido": ("circle-x", "erro")}.get(
            self._estado, ("upload", "texto_terciario"))
        self._icone.setPixmap(pixmap_icone(nome, tom, DIMENSAO["icone_grande"] - 4))

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        fundo, borda = {
            "arrastando": ("primaria_suave", "primaria"),
            "invalido": ("erro_suave", "erro"),
        }.get(self._estado, ("superficie", "borda_controle"))
        caneta = QPen(QColor(cor(borda)), 1.5 if self._estado == "normal" else 2)
        caneta.setDashPattern([4, 3])
        p.setPen(caneta)
        p.setBrush(QColor(cor(fundo)))
        r = self.rect().adjusted(1, 1, -1, -1)
        p.drawRoundedRect(r, RAIO["md"], RAIO["md"])
        p.end()
