"""Importar dados (cadastro+): equipamento + pasta/.zip/.rar, importação numa
thread com progresso e, no fim, o resumo do backend."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QVBoxLayout

from app import servico
from app.nucleo.tipos import ResumoEnvio
from design.componentes import (
    AreaSoltarArquivo, Botao, Cartao, FaixaAviso, PainelImportacao, ResumoImportacao, formatos, rotulo,
)
from design.tema import DIMENSAO, ESPACO

from .. import tarefas
from ..contexto import rotulo_equipamento
from ..erros import TarefaCancelada, traduzir_aviso
from .comum import PaginaBase

MAX_IGNORADOS_MOSTRADOS = 8


class PaginaImportacao(PaginaBase):
    depende_de = ("equipamentos",)

    def __init__(self, ctx, equipamento=None, embutida: bool = False):
        super().__init__(ctx, "Importar dados",
                         "Envie os arquivos de um equipamento para o banco. Leituras repetidas são reconhecidas "
                         "e não entram duas vezes.", embutida=embutida)
        self.fixo = equipamento          # na página do equipamento: só ele
        self.sugestao: list = []
        self.tarefa: tarefas.Tarefa | None = None
        self.ultimo_resumo: ResumoEnvio | None = None

        origem = Cartao("Origem dos dados")
        form = QHBoxLayout()
        form.setSpacing(ESPACO["xl"])
        col = QVBoxLayout()
        col.setSpacing(ESPACO["xs"])
        col.addWidget(rotulo("Equipamento", "rotulo_campo"))
        self.equipamento = QComboBox()
        self.equipamento.setAccessibleName("Equipamento")
        self.equipamento.setFixedWidth(DIMENSAO["largura_formulario"])
        col.addWidget(self.equipamento)
        form.addLayout(col)
        form.setAlignment(col, Qt.AlignmentFlag.AlignTop)
        info = QVBoxLayout()
        info.setSpacing(ESPACO["xs"])
        info.addWidget(rotulo("Local", "rotulo_campo"))
        self.local = rotulo("", "secundario")
        self.local.setMinimumHeight(DIMENSAO["altura_controle"])
        info.addWidget(self.local)
        form.addLayout(info)
        form.setAlignment(info, Qt.AlignmentFlag.AlignTop)
        form.addStretch(1)
        origem.corpo.addLayout(form)

        self.sem_equipamento = FaixaAviso("", "info")
        origem.corpo.addWidget(self.sem_equipamento)
        self.area = AreaSoltarArquivo()
        origem.corpo.addWidget(self.area)
        acoes = QHBoxLayout()
        acoes.addWidget(rotulo("Formatos aceitos: pasta do cartão SD, pasta de uma medição, .zip ou .rar. "
                               "Os arquivos são lidos no lugar, sem cópia.", "legenda"))
        acoes.addStretch(1)
        self.importar = Botao("Importar", "primaria", "upload")
        self.importar.setEnabled(False)
        acoes.addWidget(self.importar)
        origem.corpo.addLayout(acoes)
        self.corpo.addWidget(origem)

        self.painel = PainelImportacao()
        self.painel.hide()
        self.painel.ver_historico.connect(lambda: ctx.ir_para("historico"))
        self.painel.cancelar_solicitado.connect(self.cancelar)
        self.corpo.addWidget(self.painel)

        self.avisos = Cartao("Avisos do envio")
        self.avisos.hide()
        self.corpo.addWidget(self.avisos)
        self.corpo.addStretch(1)

        self.sugerido = FaixaAviso("", "alerta")
        origem.corpo.insertWidget(origem.corpo.indexOf(self.area) + 1, self.sugerido)
        self.equipamento.setEnabled(self.fixo is None)
        self.equipamento.currentIndexChanged.connect(self._ao_mudar_equipamento)
        self.area.caminho_escolhido.connect(self._sugerir_tipo)
        self.area.caminho_escolhido.connect(lambda _: self._atualizar_botao())
        self.area.caminho_rejeitado.connect(lambda *_: self._atualizar_botao())
        self.importar.clicked.connect(self.iniciar_importacao)

    # ------------------------------------------------------------------ dados
    def recarregar(self) -> None:
        atual = self.equipamento.currentData()
        try:
            equipamentos = servico.listar_equipamentos(self.ctx.usuario)   # só os ativos
            # só tipos com plugin carregado: sem ele não há quem leia os arquivos
            com_plugin = {t.codigo for t in servico.listar_tipos_sensor()}
            equipamentos = [e for e in equipamentos if e.tipo_sensor in com_plugin]
            if self.fixo is not None:
                equipamentos = [e for e in equipamentos if e.id == self.fixo.id]
        except Exception as erro:  # noqa: BLE001
            self.mostrar_erro(erro, "listar equipamentos")
            return
        self._equipamentos = {e.id: e for e in equipamentos}
        self.equipamento.blockSignals(True)
        self.equipamento.clear()
        for e in equipamentos:
            self.equipamento.addItem(rotulo_equipamento(e, com_tipo=True, ctx=self.ctx), e.id)
        indice = self.equipamento.findData(atual)
        self.equipamento.setCurrentIndex(indice if indice >= 0 else 0)
        self.equipamento.blockSignals(False)
        if equipamentos:
            self.sem_equipamento.limpar()
        elif self.fixo is not None:
            motivo = ("o plugin do tipo dele não está carregado" if self.fixo.ativo else "ele está desativado")
            self.sem_equipamento.mostrar(f"Não é possível importar para este equipamento: {motivo}.", "info")
        else:
            self.sem_equipamento.mostrar("Nenhum equipamento ativo com o plugin do tipo carregado. Cadastre um na página "
                                         "Equipamentos antes de importar.",
                                         "info")
        self._ao_mudar_equipamento()

    def _ao_mudar_equipamento(self, *_):
        eq = getattr(self, "_equipamentos", {}).get(self.equipamento.currentData())
        self.local.setText((eq.local or formatos.TRACO) if eq else formatos.TRACO)
        self._mostrar_sugestao()
        self._atualizar_botao()

    # ------------------------------------------------------------------ sugestão de tipo
    def _sugerir_tipo(self, caminho: str) -> None:
        """Pergunta aos plugins "isto é seu?" (só a estrutura) numa thread."""
        self.sugestao = []
        self.sugerido.limpar()
        tarefas.executar(servico.sugerir_tipo, [caminho], ao_concluir=self._sugestao_pronta,
                         ao_falhar=lambda _e: None, nome="sugerir tipo")

    def _sugestao_pronta(self, tipos) -> None:
        self.sugestao = list(tipos)
        self._mostrar_sugestao()

    def _mostrar_sugestao(self) -> None:
        eq = getattr(self, "_equipamentos", {}).get(self.equipamento.currentData())
        if eq is None or self.area.caminho is None or not self.sugestao:
            self.sugerido.limpar()
            return
        codigos = {t.codigo for t in self.sugestao}
        if eq.tipo_sensor in codigos:
            self.sugerido.limpar()
            return
        nomes = ", ".join(t.nome for t in self.sugestao)
        self.sugerido.mostrar(f"Estes arquivos parecem ser de {nomes}, mas {eq.nome} é "
                              f"{self.ctx.nome_tipo(eq.tipo_sensor)}. Confira o equipamento escolhido.", "alerta")

    def _ocupado(self) -> bool:
        return self.tarefa is not None and not self.tarefa.terminada

    def _atualizar_botao(self) -> None:
        pronto = (self.equipamento.currentData() is not None and self.area.caminho is not None
                  and self.area.validar(self.area.caminho) is None)
        self.importar.setEnabled(pronto and not self._ocupado())

    # ------------------------------------------------------------------ importação
    def iniciar_importacao(self) -> None:
        eq_id = self.equipamento.currentData()
        caminho = self.area.caminho
        if eq_id is None or not caminho or self._ocupado():
            return
        self.aviso.limpar()
        self.avisos.hide()
        self.painel.show()
        self.painel.iniciar(0, "Examinando os arquivos…")
        self.painel.titulo.setText(f"Importando {Path(caminho).name}…")
        for w in (self.importar, self.equipamento, self.area):
            w.setEnabled(False)
        self.tarefa = tarefas.executar(
            servico.importar_caminho, self.ctx.usuario, eq_id, caminho,
            ao_concluir=self._concluida, ao_falhar=self._falhou, ao_progresso=self._progresso,
            nome="importação")

    def cancelar(self) -> None:
        if self._ocupado():
            self.tarefa.cancelar()
            self.painel.mensagem.setText("Cancelando…")

    def _progresso(self, etapa: str, feitos: int, total: int | None) -> None:
        if etapa == "lendo":
            self.painel.mensagem.setText(f"Examinando os arquivos… {formatos.inteiro(feitos)} encontrados")
        elif etapa == "interpretando" and total:
            if self.painel.barra.maximum() != total:
                self.painel.barra.setRange(0, total)
            texto = ("Gravando no banco e conferindo duplicadas…" if feitos >= total
                     else "Interpretando as leituras…")
            self.painel.atualizar(feitos, total, texto)
        elif etapa == "concluido":
            self.painel.mensagem.setText("Concluindo…")

    def _concluida(self, r: ResumoEnvio) -> None:
        self.ultimo_resumo = r
        self._liberar()
        self.painel.concluir(ResumoImportacao(
            novas=r.novas, duplicadas=r.duplicadas, corrompidas=r.corrompidas, ignoradas=r.ignorados,
            inicio=r.inicio, fim=r.fim, arquivos=r.arquivos_recebidos))
        # o backend informa o período do envio inteiro (novas + duplicadas)
        self.painel.periodo_titulo.setText("Período coberto pelo envio")
        self.painel.periodo.setText(formatos.periodo(r.inicio, r.fim) if r.leituras else "Nenhuma leitura")
        self.painel.mensagem.setText(
            f"{formatos.inteiro(r.arquivos_recebidos)} arquivos examinados em {formatos.numero(r.duracao_s, 1, 's')}")
        if r.novas == 0 and r.leituras:
            self.painel.aviso.mostrar("Nenhuma leitura nova: todas já estavam no banco para este equipamento. "
                                      "Nada foi duplicado.", "info")
        elif r.corrompidas:
            self.painel.aviso.mostrar(
                f"{formatos.inteiro(r.corrompidas)} leitura(s) corrompida(s) ficaram guardadas só para diagnóstico "
                "(não entram nos gráficos nem nas contas). Os demais dados foram importados normalmente.", "alerta")
        elif r.leituras == 0:
            self.painel.aviso.mostrar("Nenhuma leitura deste sensor foi encontrada. Confira o equipamento escolhido "
                                      "e se a pasta é a do cartão SD.", "alerta")
        self._mostrar_avisos(r)
        self.ctx.dados_alterados.emit("envios")

    def _mostrar_avisos(self, r: ResumoEnvio) -> None:
        while self.avisos.corpo.count() > 1:
            w = self.avisos.corpo.takeAt(1).widget()
            if w is not None:
                w.hide()
                w.setParent(None)
                w.deleteLater()
        linhas = [traduzir_aviso(a) for a in r.avisos]
        if r.arquivos_ignorados:
            nomes = ", ".join(r.arquivos_ignorados[:MAX_IGNORADOS_MOSTRADOS])
            resto = r.ignorados - min(len(r.arquivos_ignorados), MAX_IGNORADOS_MOSTRADOS)
            linhas.append(f"Arquivos ignorados (não são leituras do sensor): {nomes}"
                          + (f" e mais {formatos.inteiro(resto)}." if resto > 0 else "."))
        if r.ocorrencias:
            linhas.insert(0, f"As regras de qualidade marcaram {formatos.inteiro(r.ocorrencias)} ocorrência(s) neste "
                             "envio. Os dados entraram sem alteração; veja a aba Qualidade do equipamento.")
        for texto in linhas:
            self.avisos.corpo.addWidget(rotulo(f"• {texto}", "secundario", quebra=True))
        self.avisos.setVisible(bool(linhas))

    def _falhou(self, erro: BaseException) -> None:
        self._liberar()
        texto = self.ctx.tratar_erro(erro, "importação")
        self.painel.falhar(texto)
        if isinstance(erro, TarefaCancelada):
            self.painel.titulo.setText("Importação cancelada")
            self.painel.aviso.mostrar("Importação cancelada. Nada foi gravado no banco.", "alerta")

    def _liberar(self) -> None:
        for w in (self.equipamento, self.area):
            w.setEnabled(True)
        self._atualizar_botao()
