"""Progresso e resumo da importação de dados."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QProgressBar, QVBoxLayout, QWidget

from ..tema import ESPACO, repolir
from . import formatos
from .base import Botao, rotulo
from .dialogos import FaixaAviso


@dataclass
class ResumoImportacao:
    """Resultado de uma importação (o backend devolve isto)."""

    novas: int = 0
    duplicadas: int = 0
    corrompidas: int = 0
    ignoradas: int = 0
    inicio: datetime | None = None   # primeira leitura nova
    fim: datetime | None = None      # última leitura nova
    arquivos: int = 0                # arquivos examinados

    @property
    def total(self) -> int:
        return self.novas + self.duplicadas + self.corrompidas + self.ignoradas


class _Contador(QWidget):
    def __init__(self, titulo: str, tom: str, dica: str):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(ESPACO["xxs"])
        self.valor = rotulo("0", "metrica_valor")
        self.valor.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.titulo = rotulo(titulo, "rotulo_campo")
        lay.addWidget(self.valor)
        lay.addWidget(self.titulo)
        self.setToolTip(dica)
        self.tom = tom

    def definir(self, n: int):
        self.valor.setText(formatos.inteiro(n))
        self.setAccessibleName(f"{self.titulo.text()}: {n}")


class PainelImportacao(QFrame):
    """Mostra o andamento (barra + mensagem) e, no fim, o resumo:
    leituras novas, duplicadas, corrompidas e ignoradas e o período coberto.

        painel.iniciar(total_arquivos)
        painel.atualizar(processados, total, "Lendo 20261003140000.txt")
        painel.concluir(ResumoImportacao(...))   # ou painel.falhar("motivo")
    """

    cancelar_solicitado = Signal()
    ver_historico = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setProperty("papel", "cartao")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(ESPACO["lg"], ESPACO["lg"], ESPACO["lg"], ESPACO["lg"])
        lay.setSpacing(ESPACO["md"])

        topo = QHBoxLayout()
        self.titulo = rotulo("Importação", "titulo_cartao")
        topo.addWidget(self.titulo, 1)
        self.porcentagem = rotulo("", "legenda", mono=True)
        topo.addWidget(self.porcentagem)
        lay.addLayout(topo)

        self.barra = QProgressBar()
        self.barra.setTextVisible(False)
        self.barra.setAccessibleName("Progresso da importação")
        lay.addWidget(self.barra)

        linha = QHBoxLayout()
        self.mensagem = rotulo("", "legenda", mono=True)
        self.mensagem.setMinimumWidth(10)
        linha.addWidget(self.mensagem, 1)
        self.botao_cancelar = Botao("Cancelar", "fantasma")
        self.botao_cancelar.clicked.connect(self.cancelar_solicitado)
        linha.addWidget(self.botao_cancelar)
        lay.addLayout(linha)

        self.aviso = FaixaAviso()
        lay.addWidget(self.aviso)

        self.resumo = QWidget()
        grade = QGridLayout(self.resumo)
        grade.setContentsMargins(0, ESPACO["xs"], 0, 0)
        grade.setHorizontalSpacing(ESPACO["xl"])
        grade.setVerticalSpacing(ESPACO["md"])
        self.c_novas = _Contador("Leituras novas", "sucesso", "Gravadas no banco nesta importação.")
        self.c_dup = _Contador("Duplicadas", "neutro", "Já estavam no banco (mesmo equipamento e horário); não foram gravadas de novo.")
        self.c_corr = _Contador("Corrompidas", "erro", "Arquivos ilegíveis ou incompletos; não foram gravados.")
        self.c_ign = _Contador("Ignoradas", "neutro", "Arquivos que não são leituras do sensor (outros nomes ou formatos).")
        for i, c in enumerate((self.c_novas, self.c_dup, self.c_corr, self.c_ign)):
            grade.addWidget(c, 0, i)
        self.periodo_titulo = rotulo("Período coberto pelas leituras novas", "rotulo_campo")
        self.periodo = rotulo("", None, mono=True)
        grade.addWidget(self.periodo_titulo, 1, 0, 1, 4)
        grade.addWidget(self.periodo, 2, 0, 1, 4)
        grade.setColumnStretch(4, 1)
        lay.addWidget(self.resumo)

        acoes = QHBoxLayout()
        acoes.addStretch(1)
        self.botao_historico = Botao("Ver no histórico", "secundaria", "history")
        self.botao_historico.clicked.connect(self.ver_historico)
        acoes.addWidget(self.botao_historico)
        self._acoes = acoes
        lay.addLayout(acoes)
        self.reiniciar()

    def reiniciar(self) -> None:
        self.titulo.setText("Importação")
        self.barra.setValue(0)
        self.barra.setProperty("estado", "")
        repolir(self.barra)
        self.mensagem.setText("Aguardando…")
        self.porcentagem.setText("")
        self.botao_cancelar.show()
        self.aviso.limpar()
        self.resumo.hide()
        self.botao_historico.hide()

    def iniciar(self, total: int, mensagem: str = "Preparando…") -> None:
        self.reiniciar()
        self.titulo.setText("Importando…")
        self.barra.setRange(0, max(total, 0))  # total 0 = indeterminado
        self.mensagem.setText(mensagem)

    def atualizar(self, processados: int, total: int | None = None, mensagem: str = "") -> None:
        if total is not None:
            self.barra.setMaximum(total)
        self.barra.setValue(processados)
        maximo = self.barra.maximum()
        if maximo:
            self.porcentagem.setText(f"{formatos.inteiro(processados)} de {formatos.inteiro(maximo)} arquivos · "
                                     f"{round(100 * processados / maximo)}%")
        if mensagem:
            self.mensagem.setText(mensagem)

    def concluir(self, resumo: ResumoImportacao) -> None:
        self.titulo.setText("Importação concluída")
        self.barra.setRange(0, 1)
        self.barra.setValue(1)
        self.barra.setProperty("estado", "sucesso")
        repolir(self.barra)
        self.botao_cancelar.hide()
        self.mensagem.setText(f"{formatos.inteiro(resumo.arquivos)} arquivos examinados")
        self.porcentagem.setText("100%")
        self.c_novas.definir(resumo.novas)
        self.c_dup.definir(resumo.duplicadas)
        self.c_corr.definir(resumo.corrompidas)
        self.c_ign.definir(resumo.ignoradas)
        self.periodo.setText(formatos.periodo(resumo.inicio, resumo.fim) if resumo.novas
                             else "Nenhuma leitura nova")
        if resumo.corrompidas:
            self.aviso.mostrar(f"{formatos.inteiro(resumo.corrompidas)} arquivo(s) corrompido(s) não foram gravados. "
                               "Os demais dados foram importados normalmente.", "alerta")
        elif resumo.novas == 0:
            self.aviso.mostrar("Nenhuma leitura nova: todos os arquivos já estavam no banco.", "info")
        else:
            self.aviso.mostrar(f"{formatos.inteiro(resumo.novas)} leituras novas gravadas.", "sucesso")
        self.resumo.show()
        self.botao_historico.show()

    def falhar(self, mensagem: str) -> None:
        self.titulo.setText("A importação não foi concluída")
        self.barra.setProperty("estado", "erro")
        repolir(self.barra)
        self.botao_cancelar.hide()
        self.aviso.mostrar(mensagem, "erro")
        self.resumo.hide()
