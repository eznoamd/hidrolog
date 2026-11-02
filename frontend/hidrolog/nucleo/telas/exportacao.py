"""Exportar: equipamento, período e formato; salva onde o usuário escolher,
numa thread, e mostra o resumo do backend."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from PySide6.QtCore import QDate, QStandardPaths, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QCheckBox, QComboBox, QFileDialog, QGridLayout, QHBoxLayout

from app import servico
from app.nucleo.tipos import ResumoExportacao
from design.componentes import Botao, Cartao, EstadoVazio, SeletorEquipamentoPeriodo, formatos, rotulo
from design.tema import DIMENSAO, ESPACO

from .. import tarefas
from ..contexto import rotulo_equipamento
from .comum import PaginaBase, fim_do_dia, inicio_do_dia, tamanho_arquivo
from .historico import LIMITE_HISTORICO


class PaginaExportacao(PaginaBase):
    depende_de = ("equipamentos", "envios")

    def __init__(self, ctx, equipamento=None, embutida: bool = False):
        super().__init__(ctx, "Exportar dados",
                         "Gera um arquivo com as leituras de um equipamento, para abrir em planilhas, R, Python etc.",
                         embutida=embutida)
        self.fixo = equipamento          # na página do equipamento: só ele
        self.tarefa: tarefas.Tarefa | None = None
        self.ultimo: ResumoExportacao | None = None

        self.vazio = EstadoVazio("Nenhum equipamento cadastrado", "Cadastre um equipamento e importe dados para exportar.",
                                 "cpu")
        self.vazio.hide()
        self.corpo.addWidget(self.vazio)

        self.form = Cartao("O que exportar")
        g = QGridLayout()
        g.setHorizontalSpacing(ESPACO["xl"])
        g.setVerticalSpacing(ESPACO["xs"])
        g.addWidget(rotulo("Equipamento e período", "rotulo_campo"), 0, 0)
        self.seletor = SeletorEquipamentoPeriodo([])
        g.addWidget(self.seletor, 1, 0)
        self.tudo = QCheckBox("Todo o período")
        self.tudo.setChecked(True)
        self.tudo.setMinimumHeight(DIMENSAO["altura_controle"])
        g.addWidget(self.tudo, 1, 1)
        g.addWidget(rotulo("Formato", "rotulo_campo"), 2, 0)
        self.formato = QComboBox()
        self.formato.setAccessibleName("Formato")
        self.formato.setMinimumWidth(DIMENSAO["largura_formulario"])
        g.addWidget(self.formato, 3, 0, 1, 2, Qt.AlignmentFlag.AlignLeft)
        g.setRowMinimumHeight(2, DIMENSAO["altura_controle"] - ESPACO["sm"])
        g.setColumnStretch(2, 1)
        self.form.corpo.addLayout(g)
        self.periodo_dados = rotulo("", "legenda")
        self.form.corpo.addWidget(self.periodo_dados)
        acoes = QHBoxLayout()
        acoes.addWidget(rotulo("As leituras corrompidas também vão para o arquivo, marcadas na coluna “corrompido”, "
                               "e a coluna “qualidade” traz as regras que marcaram cada leitura.", "legenda"))
        acoes.addStretch(1)
        self.exportar = Botao("Exportar…", "primaria", "download")
        acoes.addWidget(self.exportar)
        self.form.corpo.addLayout(acoes)
        self.corpo.addWidget(self.form)

        self.resultado = Cartao("Arquivo gerado")
        r = QGridLayout()
        r.setHorizontalSpacing(ESPACO["lg"])
        r.setVerticalSpacing(ESPACO["sm"])
        self.r_valores = {}
        for i, (chave, titulo) in enumerate((("caminho", "Arquivo"), ("formato", "Formato"),
                                              ("leituras", "Leituras"), ("periodo", "Período exportado"),
                                              ("tamanho", "Tamanho"))):
            r.addWidget(rotulo(titulo, "rotulo_campo"), i, 0)
            v = rotulo("", None, mono=True, quebra=True)
            v.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            r.addWidget(v, i, 1)
            self.r_valores[chave] = v
        r.setColumnStretch(1, 1)
        self.resultado.corpo.addLayout(r)
        linha = QHBoxLayout()
        linha.addStretch(1)
        self.abrir_pasta = Botao("Abrir pasta", "secundaria", "folder-open")
        self.abrir_pasta.clicked.connect(self._abrir_pasta)
        linha.addWidget(self.abrir_pasta)
        self.resultado.corpo.addLayout(linha)
        self.resultado.hide()
        self.corpo.addWidget(self.resultado)
        self.corpo.addStretch(1)

        self.seletor.equipamento.currentIndexChanged.connect(self._ao_mudar_equipamento)
        self.tudo.toggled.connect(self._ao_marcar_tudo)
        self.exportar.clicked.connect(self.escolher_destino)

    # ------------------------------------------------------------------ dados
    def recarregar(self) -> None:
        try:
            equipamentos = servico.listar_equipamentos(self.ctx.usuario, incluir_inativos=True)
            if self.fixo is not None:
                equipamentos = [e for e in equipamentos if e.id == self.fixo.id]
            self._envios = servico.listar_envios(self.ctx.usuario, self.fixo.id if self.fixo else None,
                                                 limite=LIMITE_HISTORICO)
        except Exception as erro:  # noqa: BLE001
            self.mostrar_erro(erro, "exportação")
            return
        self._equipamentos = {e.id: e for e in equipamentos}
        combo = self.seletor.equipamento
        atual = combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        for e in equipamentos:
            combo.addItem(rotulo_equipamento(e, com_tipo=True, ctx=self.ctx), e.id)
        i = combo.findData(atual)
        combo.setCurrentIndex(i if i >= 0 else 0)
        combo.blockSignals(False)
        self.vazio.setVisible(not equipamentos)
        self.form.setVisible(bool(equipamentos))
        combo.setEnabled(self.fixo is None)
        self._ao_mudar_equipamento()

    def _periodo_com_dados(self, eq_id) -> tuple:
        envios = [r for r in getattr(self, "_envios", []) if r.equipamento_id == eq_id and r.inicio]
        if not envios:
            return None, None
        return min(r.inicio for r in envios), max(r.fim for r in envios)

    def _ao_mudar_equipamento(self, *_):
        eq_id = self.seletor.equipamento.currentData()
        self.formato.clear()
        if eq_id is None:
            return
        try:
            for f in servico.listar_formatos_exportacao(eq_id):
                self.formato.addItem(f"{f.nome} · {f.extensao}", f)
        except Exception as erro:  # noqa: BLE001
            self.mostrar_erro(erro, "formatos de exportação")
        ini, fim = self._periodo_com_dados(eq_id)
        hoje = date.today()
        for campo, valor in ((self.seletor.inicio, ini), (self.seletor.fim, fim)):
            d = valor.date() if valor else hoje
            campo.setDate(QDate(d.year, d.month, d.day))
        self.periodo_dados.setText(f"Dados no banco: {formatos.periodo(ini, fim)}" if ini else
                                   "Este equipamento ainda não tem dados importados.")
        sem_formato = self.formato.count() == 0
        self.exportar.setEnabled(not sem_formato)
        if sem_formato:
            self.periodo_dados.setText("Este tipo de sensor ainda não tem formato de exportação.")
        self._ao_marcar_tudo(self.tudo.isChecked())

    def _ao_marcar_tudo(self, marcado: bool) -> None:
        self.seletor.inicio.setEnabled(not marcado)
        self.seletor.fim.setEnabled(not marcado)

    def periodo(self) -> tuple:
        if self.tudo.isChecked():
            return None, None
        _, ini, fim = self.seletor.valores()
        return inicio_do_dia(ini), fim_do_dia(fim)

    # ------------------------------------------------------------------ exportação
    def nome_sugerido(self) -> str:
        eq = self._equipamentos.get(self.seletor.equipamento.currentData())
        f = self.formato.currentData()
        base = "".join(c if c.isalnum() or c in "-_" else "_" for c in (eq.nome if eq else "dados")).strip("_")
        ini, fim = self.periodo()
        if ini:
            base += f"_{ini:%Y%m%d}_{fim:%Y%m%d}"
        return base + (f.extensao if f else "")

    def escolher_destino(self) -> None:
        f = self.formato.currentData()
        if f is None or self._ocupado():
            return
        pasta = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DownloadLocation) or str(Path.home())
        caminho, _ = QFileDialog.getSaveFileName(self, "Salvar exportação", str(Path(pasta) / self.nome_sugerido()),
                                                 f"{f.nome} (*{f.extensao})")
        if caminho:
            if not caminho.lower().endswith(f.extensao):
                caminho += f.extensao
            self.exportar_para(caminho)

    def _ocupado(self) -> bool:
        return self.tarefa is not None and not self.tarefa.terminada

    def exportar_para(self, caminho: str) -> None:
        eq_id = self.seletor.equipamento.currentData()
        f = self.formato.currentData()
        ini, fim = self.periodo()
        self.aviso.mostrar(f"Exportando para {Path(caminho).name}…", "info")
        self.exportar.setEnabled(False)
        self.resultado.hide()
        self.tarefa = tarefas.executar(servico.exportar, self.ctx.usuario, eq_id, ini, fim, f.codigo, caminho,
                                       ao_concluir=self._concluida, ao_falhar=self._falhou, nome="exportação")

    def _concluida(self, r: ResumoExportacao) -> None:
        self.ultimo = r
        self.exportar.setEnabled(True)
        self.r_valores["caminho"].setText(r.caminho)
        self.r_valores["formato"].setText(self.formato.currentText())
        self.r_valores["leituras"].setText(formatos.inteiro(r.leituras))
        self.r_valores["periodo"].setText(formatos.periodo(r.inicio, r.fim))
        self.r_valores["tamanho"].setText(tamanho_arquivo(r.tamanho_bytes))
        self.resultado.show()
        if r.leituras:
            self.aviso.mostrar(f"{formatos.inteiro(r.leituras)} leituras exportadas.", "sucesso")
        else:
            self.aviso.mostrar("Nenhuma leitura no período escolhido: o arquivo foi gerado só com o cabeçalho.",
                               "alerta")

    def _falhou(self, erro: BaseException) -> None:
        self.exportar.setEnabled(True)
        self.mostrar_erro(erro, "exportação")

    def _abrir_pasta(self) -> None:
        if self.ultimo:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(self.ultimo.caminho).parent)))
