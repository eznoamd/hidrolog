"""Tela de abertura: aparece enquanto o app abre o banco (migrações, plugins)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QVBoxLayout, QWidget

from ..tema import DIMENSAO, ESPACO
from ..tema.marca import marca_atual
from .base import rotulo
from .carregando import Carregando
from .logo import LogoMarca


class TelaAbertura(QWidget):
    """Janela pequena, sem bordas, com a logo, o nome do app e o indicador.

        abertura = TelaAbertura("Abrindo o banco de dados…"); abertura.show()
        ... trabalho em segundo plano ...
        abertura.close()
    """

    def __init__(self, texto: str = "Abrindo…", parent: QWidget | None = None):
        super().__init__(parent, Qt.WindowType.SplashScreen | Qt.WindowType.FramelessWindowHint)
        m = marca_atual()
        self.setWindowTitle(m.titulo_janela)
        self.setFixedSize(DIMENSAO["largura_login"] // 2, 300)
        externo = QVBoxLayout(self)
        externo.setContentsMargins(0, 0, 0, 0)
        cartao = QFrame()
        cartao.setProperty("papel", "cartao")
        externo.addWidget(cartao)
        lay = QVBoxLayout(cartao)
        lay.setContentsMargins(ESPACO["xxl"], ESPACO["xl"], ESPACO["xxl"], ESPACO["xl"])
        lay.setSpacing(ESPACO["md"])
        lay.addStretch(1)
        lay.addWidget(LogoMarca(altura=56, alinhamento=Qt.AlignmentFlag.AlignCenter), 0, Qt.AlignmentFlag.AlignHCenter)
        nome = rotulo(m.nome_app, "marca_app_login")
        nome.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(nome)
        self.carregando = Carregando(texto, tamanho=26)
        lay.addWidget(self.carregando)
        lay.addStretch(1)

    def definir_texto(self, texto: str) -> None:
        self.carregando.definir_texto(texto)
