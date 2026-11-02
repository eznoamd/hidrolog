"""Primeira execução: ainda não há usuário master. O app nunca cria o master;
esta tela explica o comando do backend que cria."""

from __future__ import annotations

import os
import shlex
import sys
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from design.componentes import Botao, Cartao, Divisoria, FaixaAviso, LogoMarca, rotulo
from design.tema import DIMENSAO, ESPACO, marca_atual


def pasta_backend() -> Path:
    import app

    return Path(app.__file__).resolve().parent.parent


def comando_criar_master(em_linhas: bool = False) -> str:
    """O comando exato, para rodar na pasta do backend. `em_linhas`: com a
    variável de ambiente numa linha e o comando na seguinte (com "\\" no fim
    da primeira, continua valendo se for colado no terminal)."""
    pasta = pasta_backend()
    python = "venv/bin/python" if (pasta / "venv" / "bin" / "python").exists() else (
        r"venv\Scripts\python" if (pasta / "venv" / "Scripts" / "python.exe").exists() else "python")
    comando = f'{python} -m app criar-master --login admin --nome "Seu nome"'
    dados = os.environ.get("HIDROLOG_DADOS_DIR")
    if dados:
        windows = sys.platform.startswith("win")
        prefixo = f"set HIDROLOG_DADOS_DIR={dados} && " if windows else f"HIDROLOG_DADOS_DIR={shlex.quote(dados)} "
        if em_linhas and not windows:
            prefixo += "\\\n  "
        comando = prefixo + comando
    return comando


class TelaSemMaster(QWidget):
    """Explica como criar o master pelo comando de linha. `verificar` é
    emitido em "Já criei, continuar"."""

    verificar = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        m = marca_atual()
        self.setObjectName("Fundo")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        externo = QVBoxLayout(self)
        externo.setContentsMargins(ESPACO["xl"], ESPACO["xl"], ESPACO["xl"], ESPACO["xl"])
        externo.addStretch(1)

        cartao = QFrame()
        cartao.setProperty("papel", "cartao")
        cartao.setFixedWidth(DIMENSAO["largura_login"])
        v = QVBoxLayout(cartao)
        v.setContentsMargins(ESPACO["xxxl"], ESPACO["xxl"], ESPACO["xxxl"], ESPACO["xl"])
        v.setSpacing(ESPACO["md"])
        topo = QHBoxLayout()
        topo.addWidget(LogoMarca(altura=DIMENSAO["altura_logo_lateral"] + ESPACO["md"]), 0, Qt.AlignmentFlag.AlignLeft)
        topo.addStretch(1)
        topo.addWidget(rotulo(m.nome_app, "marca_app"))
        v.addLayout(topo)
        v.addWidget(Divisoria())
        v.addSpacing(ESPACO["sm"])
        v.addWidget(rotulo("Primeira execução: falta criar o usuário master", "titulo_pagina"))
        v.addWidget(rotulo(
            "O master administra os usuários do Hidrolog. Por segurança, ele não é criado pelo app: "
            "quem instalou o sistema cria o master uma vez, pelo comando de linha do backend. "
            "Depois disso, o master entra aqui e cadastra as outras pessoas.", "secundario", quebra=True))
        v.addSpacing(ESPACO["sm"])

        v.addWidget(rotulo("1. Abra um terminal na pasta do backend", "rotulo_campo"))
        self.pasta, caixa = self._caixa_mono(str(pasta_backend()))
        v.addWidget(caixa)
        v.addWidget(rotulo("2. Rode o comando (ele pede a senha duas vezes; troque “admin” e o nome se quiser)",
                           "rotulo_campo"))
        self.comando_texto = comando_criar_master()
        self.comando, caixa = self._caixa_mono(comando_criar_master(em_linhas=True), quebrar=False)
        v.addWidget(caixa)
        linha = QHBoxLayout()
        linha.addWidget(rotulo("3. Volte aqui e continue", "rotulo_campo"))
        linha.addStretch(1)
        self.copiar = Botao("Copiar comando", "secundaria")
        self.copiar.clicked.connect(self._copiar)
        linha.addWidget(self.copiar)
        v.addLayout(linha)
        self.aviso = FaixaAviso()
        v.addWidget(self.aviso)
        acoes = QHBoxLayout()
        acoes.addWidget(rotulo(f"{m.assinatura}", "legenda"))
        acoes.addStretch(1)
        self.continuar = Botao("Já criei, continuar", "primaria", "arrow-right")
        self.continuar.clicked.connect(self.verificar)
        acoes.addWidget(self.continuar)
        v.addSpacing(ESPACO["sm"])
        v.addLayout(acoes)

        externo.addWidget(cartao, 0, Qt.AlignmentFlag.AlignHCenter)
        externo.addStretch(1)

    def _caixa_mono(self, texto: str, quebrar: bool = True) -> tuple[QLabel, Cartao]:
        """Texto em mono, selecionável, numa caixa com a borda do tema."""
        caixa = Cartao(margem=ESPACO["sm"])
        r = rotulo(texto, None, mono=True, quebra=quebrar)
        r.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        r.setAccessibleName(texto)
        caixa.corpo.addWidget(r)
        return r, caixa

    def _copiar(self) -> None:
        QGuiApplication.clipboard().setText(self.comando_texto)
        self.aviso.mostrar("Comando copiado.", "sucesso")

    def ainda_sem_master(self) -> None:
        self.aviso.mostrar("Ainda não há nenhum master neste banco. Rode o comando acima e tente de novo.", "alerta")
