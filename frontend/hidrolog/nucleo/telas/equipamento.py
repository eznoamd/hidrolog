"""Página do equipamento: cabeçalho (nome, tipo, série, local, período,
alertas) e as abas — as do plugin do tipo do equipamento e as comuns do
núcleo (Qualidade, Envios, Importar, Exportar, Cadastro).

As abas do plugin recebem o ContextoAba pronto (equipamento, período,
usuário, consultas): não há seletor de equipamento dentro delas. Um tipo sem
plugin carregado mostra só as abas comuns, com o aviso.

Os equipamentos abertos vão para a seção Recentes da barra lateral.
"""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QCheckBox, QGridLayout, QLineEdit, QVBoxLayout, QWidget

from app import servico
from app.nucleo.tipos import Equipamento
from design.componentes import (
    Abas, Botao, Cartao, Coluna, EstadoVazio, FaixaAviso, FormularioFicha, Selo, SeletorPeriodo, TabelaFiltravel,
    formatos, rotulo,
)
from design.tema import DIMENSAO, ESPACO

from .. import configuracao, registro
from .comum import DialogoFormulario, PaginaBase, fim_do_dia, inicio_do_dia
from .exportacao import PaginaExportacao
from .historico import LIMITE_HISTORICO, DialogoEnvio, colunas_historico, linha_envio
from .importacao import PaginaImportacao

PREFIXO = "equipamento."
SECAO_RECENTES = "recentes"
MAX_RECENTES = 5
ESPERA_PERIODO_MS = 350
ABAS_COMUNS = [("qualidade", "Qualidade", "triangle-alert"), ("envios", "Envios", "history"),
               ("importar", "Importar", "upload"), ("exportar", "Exportar", "download"),
               ("cadastro", "Cadastro", "pencil")]


def chave_pagina(eq_id: int) -> str:
    return f"{PREFIXO}{eq_id}"


def descricao_equipamento(ctx, eq: Equipamento) -> str:
    """'Pluviômetro de báscula · nº 450994 · Estação 1'."""
    partes = [ctx.nome_tipo(eq.tipo_sensor)]
    if eq.numero_serie:
        partes.append(f"nº {eq.numero_serie}")
    if eq.local:
        partes.append(eq.local)
    if not eq.ativo:
        partes.append("desativado")
    return " · ".join(partes)


# ============================================================================ abas comuns

class AbaEnvios(QWidget):
    def __init__(self, pagina: "PaginaEquipamento"):
        super().__init__()
        self.pagina = pagina
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.tabela = TabelaFiltravel(colunas_historico(compacta=True), mostrar_busca=False, ordenar_por="quando",
                                      decrescente=True, titulo_vazio="Nenhum envio ainda",
                                      descricao_vazio="Os envios deste equipamento aparecem aqui depois da "
                                                      "primeira importação.", icone_vazio="history")
        self.detalhe = Botao("Ver detalhe", "secundaria", "eye")
        self.detalhe.setEnabled(False)
        self.tabela.adicionar_acao(self.detalhe)
        self.tabela.selecao_alterada.connect(lambda s: self.detalhe.setEnabled(len(s) == 1))
        self.detalhe.clicked.connect(lambda: self.abrir_detalhe(self.tabela.selecao()[0]))
        self.tabela.linha_ativada.connect(self.abrir_detalhe)
        self.tabela.setMinimumHeight(420)
        lay.addWidget(self.tabela)

    def atualizar(self) -> None:
        envios = servico.listar_envios(self.pagina.ctx.usuario, self.pagina.eq_id, limite=LIMITE_HISTORICO)
        self.tabela.definir_linhas([linha_envio(r) for r in envios])

    def abrir_detalhe(self, linha: dict) -> DialogoEnvio | None:
        try:
            envio = servico.obter_envio(self.pagina.ctx.usuario, linha["id"])
        except Exception as erro:  # noqa: BLE001
            self.pagina.mostrar_erro(erro, "detalhe do envio")
            return None
        d = DialogoEnvio(envio, self.pagina.ctx, self.window())
        d.open()
        return d


AGUARDANDO_LEITURAS = "aguardando a primeira importação com esse campo"


def _coluna_numero_serie(tipo_sensor: str) -> str | None:
    """Coluna das leituras com o nº de série, se o plugin do tipo declarar uma."""
    try:
        from app.nucleo import plugins

        return plugins.obter(tipo_sensor).ingestao.coluna_numero_serie
    except Exception:  # noqa: BLE001 - plugin ausente ou sem ingestão: sem conferência
        return None


class AbaCadastro(QWidget):
    """Dois blocos: o que foi cadastrado (comuns + ficha editável do plugin,
    com o botão Editar para cadastro+) e o que o sensor informa nas leituras
    (nº de série registrado na primeira importação e os campos da ficha com
    origem "leituras"), com aviso se o nº de série lido não bater."""

    def __init__(self, pagina: "PaginaEquipamento"):
        super().__init__()
        self.pagina = pagina
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(ESPACO["lg"])
        self.cartao = Cartao("Cadastro do equipamento")
        self.editar = Botao("Editar", "secundaria", "pencil")
        self.editar.setVisible(pagina.ctx.pode("cadastro"))
        self.editar.clicked.connect(self.abrir_edicao)
        self.cartao.cabecalho.addWidget(self.editar)
        self.alternar = Botao("Desativar", "secundaria", "eye-off")
        self.alternar.setVisible(pagina.ctx.pode("cadastro"))
        self.alternar.clicked.connect(self.alternar_ativo)
        self.cartao.cabecalho.addWidget(self.alternar)
        self.grade = QGridLayout()
        self.grade.setHorizontalSpacing(ESPACO["xl"])
        self.grade.setVerticalSpacing(ESPACO["sm"])
        self.grade.setColumnStretch(1, 1)
        self.cartao.corpo.addLayout(self.grade)
        lay.addWidget(self.cartao)
        self.cartao_sensor = Cartao("Informado pelo sensor")
        self.cartao_sensor.corpo.addWidget(rotulo(
            "Lido automaticamente dos arquivos importados; não é editado no cadastro.", "secundario", quebra=True))
        self.aviso_serie = FaixaAviso()
        self.cartao_sensor.corpo.addWidget(self.aviso_serie)
        self.grade_sensor = QGridLayout()
        self.grade_sensor.setHorizontalSpacing(ESPACO["xl"])
        self.grade_sensor.setVerticalSpacing(ESPACO["sm"])
        self.grade_sensor.setColumnStretch(1, 1)
        self.cartao_sensor.corpo.addLayout(self.grade_sensor)
        lay.addWidget(self.cartao_sensor)
        lay.addStretch(1)
        self.valores: dict[str, str] = {}

    def linhas(self, eq: Equipamento) -> list[tuple[str, str]]:
        ctx = self.pagina.ctx
        coordenadas = (f"{formatos.numero(eq.latitude, 5)}, {formatos.numero(eq.longitude, 5)}"
                       if eq.latitude is not None and eq.longitude is not None else formatos.TRACO)
        linhas = [
            ("Nome", eq.nome), ("Tipo de sensor", ctx.nome_tipo(eq.tipo_sensor)),
            ("Local", eq.local or formatos.TRACO),
            ("Coordenadas", coordenadas),
            ("Situação", "Ativo" if eq.ativo else "Desativado"),
            ("Cadastrado em", formatos.data_hora(eq.criado_em)),
            ("Observações", eq.observacoes or formatos.TRACO),
        ]
        for campo in servico.ficha_do_tipo(eq.tipo_sensor):
            if not FormularioFicha.editavel(campo):
                continue
            linhas.append((campo.rotulo, self._texto_campo(campo, (eq.atributos or {}).get(campo.chave))))
        return linhas

    @staticmethod
    def _texto_campo(campo, valor, vazio: str = formatos.TRACO) -> str:
        if valor is None:
            return vazio
        texto = FormularioFicha._texto(campo, valor)
        return f"{texto} {campo.unidade}" if campo.unidade else texto

    def linhas_sensor(self, eq: Equipamento) -> list[tuple[str, str]]:
        """Nº de série registrado e os campos da ficha que vêm das leituras."""
        linhas = [("Nº de série registrado", eq.numero_serie or AGUARDANDO_LEITURAS)]
        for campo in servico.ficha_do_tipo(eq.tipo_sensor):
            if campo.origem == "leituras":
                linhas.append((campo.rotulo, self._texto_campo(campo, (eq.atributos or {}).get(campo.chave),
                                                               AGUARDANDO_LEITURAS)))
        return linhas

    def serie_divergente(self, eq: Equipamento) -> str | None:
        """Nº de série das leituras mais recentes, se for diferente do registrado."""
        coluna = _coluna_numero_serie(eq.tipo_sensor)
        if not coluna or not eq.numero_serie:
            return None
        for campo in servico.ficha_do_tipo(eq.tipo_sensor):
            if campo.origem == "leituras" and campo.coluna == coluna:
                lido = (eq.atributos or {}).get(campo.chave)
                if lido and str(lido).strip() != eq.numero_serie.strip():
                    return str(lido).strip()
        return None

    def atualizar(self) -> None:
        eq = self.pagina.equipamento
        self.alternar.setText(" Desativar" if eq.ativo else " Reativar")
        self.alternar.definir_icone("eye-off" if eq.ativo else "eye")
        self.valores = {}
        self.valores_sensor: dict[str, str] = {}
        self._preencher(self.grade, self.linhas(eq), self.valores)
        self._preencher(self.grade_sensor, self.linhas_sensor(eq), self.valores_sensor)
        lido = self.serie_divergente(eq)
        self.aviso_serie.mostrar(
            f"As leituras mais recentes informam o nº de série {lido}, mas o equipamento está registrado "
            f"com o nº {eq.numero_serie}. Confira se os dados importados são deste equipamento." if lido else "",
            "alerta")

    @staticmethod
    def _preencher(grade: QGridLayout, linhas: list[tuple[str, str]], valores: dict[str, str]) -> None:
        while grade.count():
            w = grade.takeAt(0).widget()
            if w is not None:
                w.hide()
                w.setParent(None)
                w.deleteLater()
        for i, (nome, valor) in enumerate(linhas):
            grade.addWidget(rotulo(nome, "rotulo_campo"), i, 0)
            grade.addWidget(rotulo(valor, None, quebra=True), i, 1)
            valores[nome] = valor

    def alternar_ativo(self):
        from .equipamentos import alternar_equipamento

        eq = self.pagina.equipamento
        novo = alternar_equipamento(self.pagina, self.pagina.ctx, eq)
        if novo is not None:
            self.pagina.ctx.dados_alterados.emit("equipamentos")
            self.pagina.mostrar_aviso(f"Equipamento {eq.nome} {'reativado' if novo.ativo else 'desativado'}.")
        return novo

    def abrir_edicao(self):
        from .equipamentos import DialogoEquipamento

        d = DialogoEquipamento(self.pagina.ctx, self.pagina.equipamento, self.window())
        d.accepted.connect(lambda: (self.pagina.ctx.dados_alterados.emit("equipamentos"),
                                    self.pagina.mostrar_aviso(f"Equipamento {d.resultado.nome} atualizado.")))
        d.open()
        return d


SEVERIDADES = {"alerta": ("Alerta", "erro"), "suspeita": ("Suspeita", "alerta"), "aviso": ("Aviso", "info")}
NIVEIS = {"leitura": "Leitura", "envio": "Envio", "equipamento": "Equipamento"}


def selo_qualidade(resumo) -> tuple[str, str]:
    """(texto, tom) do selo de qualidade de um equipamento (ResumoQualidade ou None)."""
    if resumo is None or resumo.total == 0:
        return ("OK", "sucesso")
    if resumo.alertas:
        return (f"{resumo.alertas} alerta(s)", "erro")
    if resumo.suspeitas:
        return (f"{resumo.suspeitas} suspeita(s)", "alerta")
    return (f"{resumo.avisos} aviso(s)", "info")


class DialogoRegra(DialogoFormulario):
    """Ajusta os parâmetros de uma regra só para este equipamento (cadastro+)."""

    def __init__(self, ctx, eq_id: int, regra, parent=None):
        super().__init__(f"Regra: {regra.descricao}",
                         "Os parâmetros valem só para este equipamento. Quem alterou e quando fica registrado. "
                         "As regras nunca alteram os dados: elas só marcam ocorrências.", "Salvar", parent)
        self.ctx, self.eq_id, self.regra = ctx, eq_id, regra
        self.ativa = QCheckBox("Regra ligada para este equipamento")
        self.ativa.setChecked(regra.ativa)
        self.campo("Situação", self.ativa)
        self.campos: dict[str, QLineEdit] = {}
        for chave, valor in regra.parametros.items():
            w = QLineEdit(f"{valor:g}".replace(".", ",") if isinstance(valor, float) else str(valor))
            padrao = regra.padrao.get(chave)
            ajuda = regra.ajuda_parametros.get(chave, "")
            ajuda = f"{ajuda} · padrão {padrao:g}".replace(".", ",") if isinstance(padrao, (int, float)) else ajuda
            self.campos[chave] = self.campo(chave.replace("_", " ").capitalize(), w, ajuda.strip(" ·"))

    def salvar(self):
        return servico.configurar_regra(self.ctx.usuario, self.eq_id, self.regra.codigo,
                                        {k: w.text().strip() for k, w in self.campos.items()},
                                        ativa=self.ativa.isChecked())

    def tratar_erro_salvar(self, erro) -> bool:
        from app.nucleo.erros import ErroValidacao

        if isinstance(erro, ErroValidacao):
            for chave, mensagem in erro.campos.items():
                if chave in self.campos:
                    self.erro_campo(self.campos[chave], erros_txt(mensagem))
            return True
        return False


def altura_tabela_embutida(linhas: int) -> int:
    from .inicio import altura_tabela
    return altura_tabela(linhas) + DIMENSAO["altura_controle"] + ESPACO["sm"]


def erros_txt(texto: str) -> str:
    from ..erros import acentuar
    return acentuar(texto)


class AbaQualidade(QWidget):
    """Ocorrências de qualidade do equipamento e as regras do plugin, com os
    parâmetros valendo para ele (ajustáveis pelo perfil cadastro ou superior)."""

    def __init__(self, pagina: "PaginaEquipamento"):
        super().__init__()
        self.pagina = pagina
        ctx = pagina.ctx
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(ESPACO["lg"])
        self.tabela = TabelaFiltravel([
            Coluna("severidade", "Severidade", "selo", selo=lambda v: SEVERIDADES.get(v, (v, "neutro")), largura=110),
            Coluna("regra", "Regra", "mono", largura=190),
            Coluna("nivel", "Nível", largura=120),
            Coluna("tempo", "Quando", "data_hora", largura=136),
            Coluna("mensagem", "O que foi encontrado", estica=True),
            Coluna("situacao", "Situação", "selo",
                   selo=lambda v: ("Aberta", "alerta") if v == "aberta" else ("Resolvida", "neutro"), largura=110),
        ], texto_busca="Buscar na mensagem ou na regra…", titulo_vazio="Nenhuma ocorrência de qualidade",
            descricao_vazio="As regras do sensor não encontraram nada neste equipamento.", icone_vazio="circle-check")
        self.filtro = self.tabela.adicionar_filtro("severidade", "Todas as severidades")
        self.mostrar_resolvidas = QCheckBox("Mostrar resolvidas")
        self.mostrar_resolvidas.toggled.connect(lambda _: self.atualizar())
        self.tabela.adicionar_acao(self.mostrar_resolvidas)
        self.resolver = Botao("Marcar como resolvida", "secundaria", "check")
        self.resolver.setEnabled(False)
        self.resolver.setVisible(ctx.pode("cadastro"))
        self.resolver.clicked.connect(self.resolver_selecionadas)
        self.tabela.adicionar_acao(self.resolver)
        self.tabela.selecao_alterada.connect(
            lambda sel: self.resolver.setEnabled(any(l["situacao"] == "aberta" for l in sel)))
        self.tabela.setMinimumHeight(320)
        lay.addWidget(self.tabela)

        self.cartao_regras = Cartao("Regras deste equipamento")
        self.cartao_regras.corpo.addWidget(rotulo(
            "As regras vêm do plugin do sensor e nunca alteram os dados. Leituras suspeitas entram nos gráficos com "
            "destaque (use “Ocultar suspeitas” no cabeçalho) e as exportações levam a coluna de qualidade.",
            "secundario", quebra=True))
        self.regras = TabelaFiltravel([
            Coluna("descricao", "Regra", largura=360),
            Coluna("nivel", "Nível", largura=120),
            Coluna("severidade", "Severidade", "selo", selo=lambda v: SEVERIDADES.get(v, (v, "neutro")), largura=110),
            Coluna("parametros", "Parâmetros", "mono", estica=True),
            Coluna("ativa", "Situação", "selo", selo=lambda v: ("Ligada", "sucesso") if v else ("Desligada", "neutro"),
                   largura=100),
            Coluna("alterada", "Alterada", largura=190),
        ], mostrar_busca=False, embutida=True, titulo_vazio="Este sensor não tem regras de qualidade",
            icone_vazio="layers")
        self.ajustar = Botao("Ajustar regra", "secundaria", "settings")
        self.ajustar.setEnabled(False)
        self.ajustar.setVisible(ctx.pode("cadastro"))
        self.ajustar.clicked.connect(lambda: self.abrir_regra(self.regras.selecao()[0]["_regra"]))
        self.regras.adicionar_acao(self.ajustar)
        self.regras.selecao_alterada.connect(lambda sel: self.ajustar.setEnabled(len(sel) == 1))
        if ctx.pode("cadastro"):
            self.regras.linha_ativada.connect(lambda linha: self.abrir_regra(linha["_regra"]))
        self.regras.setMinimumHeight(200)
        self.cartao_regras.corpo.addWidget(self.regras)
        lay.addWidget(self.cartao_regras)
        lay.addStretch(1)

    def atualizar(self) -> None:
        u = self.pagina.ctx.usuario
        abertas = None if self.mostrar_resolvidas.isChecked() else True
        ocorrencias = servico.listar_ocorrencias(u, self.pagina.eq_id, abertas=abertas)
        self.tabela.definir_linhas([
            {"severidade": o.severidade, "regra": o.codigo_regra, "nivel": NIVEIS.get(o.nivel, o.nivel),
             "tempo": o.tempo, "mensagem": erros_txt(o.mensagem),
             "situacao": "aberta" if o.resolvida_em is None else "resolvida", "_o": o} for o in ocorrencias])
        linhas = []
        for r in servico.listar_regras(u, self.pagina.eq_id):
            parametros = ", ".join(f"{k} = {v:g}".replace(".", ",") if isinstance(v, (int, float)) else f"{k} = {v}"
                                   for k, v in r.parametros.items()) or formatos.TRACO
            alterada = (f"{r.alterada_por} · {formatos.data_hora(r.alterada_em)}" if r.alterada_em
                        else "padrão do plugin")
            linhas.append({"descricao": r.descricao, "nivel": NIVEIS.get(r.nivel, r.nivel), "severidade": r.severidade,
                           "parametros": parametros, "ativa": r.ativa, "alterada": alterada, "_regra": r})
        self.regras.definir_linhas(linhas)
        self.regras.setFixedHeight(altura_tabela_embutida(len(linhas)))
        self.tabela.setFixedHeight(max(altura_tabela_embutida(min(max(len(ocorrencias), 3), 12)) + 48, 220))

    def resolver_selecionadas(self) -> None:
        u = self.pagina.ctx.usuario
        try:
            for linha in self.tabela.selecao():
                if linha["situacao"] == "aberta":
                    servico.resolver_ocorrencia(u, linha["_o"].id)
        except Exception as erro:  # noqa: BLE001
            self.pagina.mostrar_erro(erro, "resolver ocorrência")
        self.pagina.ctx.dados_alterados.emit("qualidade")

    def abrir_regra(self, regra) -> "DialogoRegra":
        d = DialogoRegra(self.pagina.ctx, self.pagina.eq_id, regra, self.window())
        d.accepted.connect(lambda: (self.pagina.ctx.dados_alterados.emit("qualidade"),
                                    self.pagina.mostrar_aviso(f"Regra “{regra.descricao}” ajustada para este "
                                                              "equipamento.")))
        d.open()
        return d


# ============================================================================ página

class PaginaEquipamento(PaginaBase):
    depende_de = ("envios", "equipamentos", "qualidade")

    def __init__(self, ctx, eq_id: int):
        super().__init__(ctx, "Equipamento")
        self.eq_id = eq_id
        self.equipamento: Equipamento = servico.obter_equipamento(ctx.usuario, eq_id)
        self.inicio: date | None = None
        self.fim: date | None = None
        self.ocultar = False
        self._contexto_mostrado: dict[str, tuple] = {}

        self.alertas = Selo("", "erro")
        self.alertas.hide()
        self.ocultar_suspeitas = QCheckBox("Ocultar suspeitas")
        self.ocultar_suspeitas.setToolTip("Tira dos gráficos as leituras marcadas como suspeitas pelas regras de "
                                          "qualidade (os dados não mudam)")
        self.periodo = SeletorPeriodo()
        self.adicionar_acao(self.alertas)
        self.adicionar_acao(self.ocultar_suspeitas)
        self.adicionar_acao(self.periodo)
        self._espera = QTimer(self)
        self._espera.setSingleShot(True)
        self._espera.setInterval(ESPERA_PERIODO_MS)
        self._espera.timeout.connect(lambda: self.definir_periodo(*self.periodo.valores()))
        self.periodo.alterado.connect(lambda *_: self._espera.start())
        self.periodo.tudo_solicitado.connect(self.periodo_completo)
        self.ocultar_suspeitas.toggled.connect(self._ao_ocultar)

        self.sem_plugin = FaixaAviso("", "alerta")
        self.corpo.addWidget(self.sem_plugin)
        self.abas = Abas()
        self.abas_plugin = registro.abas(self.equipamento.tipo_sensor) or []
        for aba in self.abas_plugin:
            if aba.perfis and ctx.perfil not in aba.perfis:
                continue
            self.abas.adicionar(aba.chave, aba.titulo, lambda a=aba: self._criar_aba_plugin(a),
                                dica=aba.descricao or None)
        if self.abas_plugin:
            self.abas.adicionar_separador()
        self.qualidade = AbaQualidade(self)
        self.envios = AbaEnvios(self)
        self.cadastro = AbaCadastro(self)
        comuns = {"qualidade": self.qualidade, "envios": self.envios, "cadastro": self.cadastro,
                  "importar": lambda: PaginaImportacao(ctx, self.equipamento, embutida=True),
                  "exportar": lambda: PaginaExportacao(ctx, self.equipamento, embutida=True)}
        sem_plugin = registro.plugin(self.equipamento.tipo_sensor) is None
        for chave, titulo, icone in ABAS_COMUNS:
            # importar precisa do plugin do tipo (é ele quem lê os arquivos)
            if chave == "importar" and (not ctx.pode("cadastro") or sem_plugin):
                continue
            self.abas.adicionar(chave, titulo, comuns[chave])
        self.corpo.addWidget(self.abas, 1)
        self.abas.aba_alterada.connect(self._ao_mudar_aba)
        plugin = registro.plugin(self.equipamento.tipo_sensor)
        tem_suspeitas = plugin is not None and any(r.severidade == "suspeita" for r in plugin.regras)
        self.ocultar_suspeitas.setVisible(bool(self.abas_plugin) and tem_suspeitas)
        self.periodo.setVisible(bool(self.abas_plugin))
        self._atualizar_cabecalho()
        self.inicio, self.fim = self._periodo_dos_dados()
        self.periodo.definir(self.inicio, self.fim)

    # ------------------------------------------------------------------ cabeçalho e período
    def _atualizar_selo(self) -> None:
        try:
            resumo = servico.resumo_qualidade(self.ctx.usuario).get(self.eq_id)
        except Exception as erro:  # noqa: BLE001
            self.ctx.tratar_erro(erro, "qualidade")
            return
        texto, tom = selo_qualidade(resumo)
        self.alertas.definir(f"⚠ {texto}" if resumo and resumo.total else texto, tom)
        self.alertas.setToolTip("Ocorrências de qualidade abertas (aba Qualidade)")
        self.alertas.setVisible(bool(resumo and resumo.total))

    def _atualizar_cabecalho(self) -> None:
        eq = self.equipamento
        self._atualizar_selo()
        self.titulo.setText(eq.nome)
        self.subtitulo.setText(descricao_equipamento(self.ctx, eq))
        self.subtitulo.show()
        if not self.abas_plugin:
            situacao = registro.plugin(eq.tipo_sensor)
            self.sem_plugin.mostrar(
                "Interface deste sensor indisponível: o plugin do tipo "
                f"“{self.ctx.nome_tipo(eq.tipo_sensor)}” não está carregado ou não traz abas. "
                + ("Os dados continuam no banco; use as abas comuns (inclusive a exportação do plugin)."
                   if situacao is not None else
                   "Os dados continuam no banco para consulta e exportação genérica, mas não é possível "
                   "importar dados novos até o plugin ser reativado ou instalado."), "alerta")
        else:
            self.sem_plugin.limpar()

    def _periodo_dos_dados(self) -> tuple[date, date]:
        hoje = date.today()
        try:
            r = servico.resumo_leituras(self.ctx.usuario, self.eq_id)
        except Exception as erro:  # noqa: BLE001
            self.mostrar_erro(erro, "período das leituras")
            return hoje, hoje
        if r.inicio is None:
            return hoje, hoje
        return r.inicio.date(), r.fim.date()

    def periodo_completo(self) -> None:
        self.definir_periodo(*self._periodo_dos_dados())

    def definir_periodo(self, inicio: date, fim: date) -> None:
        if inicio > fim:
            inicio, fim = fim, inicio
        self._espera.stop()
        self.periodo.definir(inicio, fim)
        if (inicio, fim) == (self.inicio, self.fim):
            return
        self.inicio, self.fim = inicio, fim
        self._atualizar_aba_atual()

    def _ao_ocultar(self, marcado: bool) -> None:
        self.ocultar = marcado
        self._atualizar_aba_atual()

    def contexto(self):
        return registro.contexto_aba(self.ctx, self.equipamento, inicio_do_dia(self.inicio), fim_do_dia(self.fim),
                                     self.ocultar)

    # ------------------------------------------------------------------ abas
    def _criar_aba_plugin(self, aba) -> QWidget:
        contexto = self.contexto()
        try:
            w = aba.fabrica(contexto)
        except Exception as erro:  # noqa: BLE001 - uma aba com defeito não derruba a página
            texto = self.ctx.tratar_erro(erro, f"abrir a aba {aba.chave}")
            w = Cartao()
            w.corpo.addWidget(EstadoVazio("Esta aba não abriu", texto, "circle-x"))
        self._contexto_mostrado[aba.chave] = contexto.chave()
        return w

    def aba_plugin(self, chave: str) -> QWidget | None:
        return self.abas.widget(chave)

    def _ao_mudar_aba(self, chave: str) -> None:
        self._atualizar_aba(chave)

    def _atualizar_aba_atual(self) -> None:
        atual = self.abas.atual()
        if atual:
            self._atualizar_aba(atual)

    def _atualizar_aba(self, chave: str) -> None:
        w = self.abas.widget(chave)
        if w is None:
            return
        try:
            if chave in self._contexto_mostrado:          # aba do plugin
                contexto = self.contexto()
                if contexto.chave() != self._contexto_mostrado[chave] and hasattr(w, "atualizar"):
                    self._contexto_mostrado[chave] = contexto.chave()
                    w.atualizar(contexto)
            elif hasattr(w, "atualizar"):
                w.atualizar()
            elif hasattr(w, "recarregar"):
                w.recarregar()
        except Exception as erro:  # noqa: BLE001
            self.mostrar_erro(erro, f"aba {chave}")

    def recarregar(self) -> None:
        try:
            self.equipamento = servico.obter_equipamento(self.ctx.usuario, self.eq_id)
        except Exception as erro:  # noqa: BLE001
            self.mostrar_erro(erro, "equipamento")
            return
        self.ctx.atualizar_recente(self.equipamento)
        self._atualizar_cabecalho()
        self._atualizar_aba_atual()

    def _ao_alterar(self, tipo: str) -> None:
        if tipo == "envios" and self.inicio is not None:
            # dados novos: o período passa a cobrir tudo o que o equipamento tem
            self.inicio, self.fim = self._periodo_dos_dados()
            self.periodo.definir(self.inicio, self.fim)
        super()._ao_alterar(tipo)


# ============================================================================ recentes

def _chave_preferencia(ctx) -> str:
    return f"recentes/{ctx.usuario.login}"


def ler_recentes(ctx) -> list[int]:
    valor = configuracao.preferencias().value(_chave_preferencia(ctx), [])
    if isinstance(valor, str):
        valor = [valor]
    saida = []
    for v in valor or []:
        try:
            saida.append(int(v))
        except (TypeError, ValueError):
            continue
    return saida[:MAX_RECENTES]


def gravar_recentes(ctx, ids: list[int]) -> None:
    p = configuracao.preferencias()
    p.setValue(_chave_preferencia(ctx), [str(i) for i in ids[:MAX_RECENTES]])
    p.sync()


def registrar_recente(shell, ctx, eq: Equipamento, primeiro: bool = True) -> None:
    """Põe o equipamento na seção Recentes (no topo) e tira o mais antigo."""
    chave = chave_pagina(eq.id)
    ids = [i for i in ler_recentes(ctx) if i != eq.id]
    ids.insert(0, eq.id) if primeiro else ids.append(eq.id)
    if not shell.tem_pagina(chave):
        shell.adicionar_pagina(chave, eq.nome, lambda: PaginaEquipamento(ctx, eq.id), "cpu",
                               secao=SECAO_RECENTES, migalha="Equipamentos")
    for antigo in ids[MAX_RECENTES:]:
        shell.remover_pagina(chave_pagina(antigo))
    ids = ids[:MAX_RECENTES]
    for ordem, i in enumerate(ids):
        p = shell._paginas.get(chave_pagina(i))
        if p is not None:
            p.ordem = ordem
    secao = shell._secoes[SECAO_RECENTES]
    secao.paginas.sort(key=lambda p: p.ordem)
    for p in secao.paginas:
        secao.itens.removeWidget(p.botao)
    for i, p in enumerate(secao.paginas):
        secao.itens.insertWidget(i, p.botao)
    gravar_recentes(ctx, ids)


def montar_recentes(shell, ctx) -> None:
    """Seção Recentes com os equipamentos abertos por último por este usuário."""
    shell.adicionar_secao(SECAO_RECENTES, "Recentes", ordem=950, recolhivel=False)
    try:
        equipamentos = {e.id: e for e in servico.listar_equipamentos(ctx.usuario, incluir_inativos=True)}
    except Exception as erro:  # noqa: BLE001
        ctx.tratar_erro(erro, "recentes")
        return
    ids = [i for i in ler_recentes(ctx) if i in equipamentos]
    for ordem, i in enumerate(ids):
        eq = equipamentos[i]
        shell.adicionar_pagina(chave_pagina(i), eq.nome, lambda e=eq: PaginaEquipamento(ctx, e.id), "cpu",
                               secao=SECAO_RECENTES, ordem=ordem, migalha="Equipamentos")
    gravar_recentes(ctx, ids)
