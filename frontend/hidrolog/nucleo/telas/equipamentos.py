"""Equipamentos: listar, filtrar por tipo, criar, editar e desativar (cadastro+).
Desativar é o "apagar" do app: o equipamento sai da lista e da importação, mas
os dados e o histórico ficam (e ele pode ser reativado)."""

from __future__ import annotations

import os

from PySide6.QtWidgets import QCheckBox, QComboBox, QHBoxLayout, QLineEdit, QPlainTextEdit, QWidget

from app import servico
from app.nucleo.erros import Conflito, ErroValidacao
from app.nucleo.tipos import Equipamento
from design.componentes import (
    Botao, Coluna, DialogoConfirmacao, FormularioFicha, MapaSeletor, TabelaFiltravel, rotulo,
)
from design.tema import DIMENSAO, ESPACO

from ..erros import acentuar

from .comum import DialogoFormulario, PaginaBase
from .historico import LIMITE_HISTORICO


class PaginaEquipamentos(PaginaBase):
    depende_de = ("equipamentos", "envios", "qualidade")

    def __init__(self, ctx):
        super().__init__(ctx, "Equipamentos",
                         "Cada unidade física cadastrada: tipo de sensor, número de série e local de instalação. "
                         "Clique duas vezes num equipamento para abrir a página dele.")
        pode = ctx.pode("cadastro")
        self.novo = Botao("Novo equipamento", "primaria", "plus")
        self.novo.clicked.connect(self.novo_equipamento)
        self.novo.setVisible(pode)
        self.adicionar_acao(self.novo)
        self.tabela = TabelaFiltravel([
            Coluna("nome", "Nome", largura=170),
            Coluna("tipo", "Tipo", largura=170),
            Coluna("serie", "Nº de série", "mono"),
            Coluna("local", "Local", estica=True),
            Coluna("criado", "Cadastrado em", "data"),
            Coluna("leituras", "Leituras", "inteiro", dica="Leituras novas gravadas pelos envios deste equipamento"),
            Coluna("ultimo", "Último envio", "data_hora"),
            Coluna("qualidade", "Qualidade", "selo", selo=lambda v: v, largura=130,
                   dica="Ocorrências de qualidade abertas (regras do sensor)"),
            Coluna("situacao", "Situação", "selo",
                   selo=lambda v: ("Ativo", "sucesso") if v == "Ativo" else ("Desativado", "neutro"), largura=120),
        ], texto_busca="Buscar por nome, série ou local…", titulo_vazio="Nenhum equipamento cadastrado",
            descricao_vazio=("Cadastre o primeiro equipamento para poder importar dados." if pode else
                             "Peça a alguém com perfil Cadastro para cadastrar os equipamentos."),
            icone_vazio="cpu")
        self.filtro_tipo = self.tabela.adicionar_filtro("tipo", "Todos os tipos")
        self.mostrar_desativados = QCheckBox("Mostrar desativados")
        self.mostrar_desativados.setToolTip("Equipamentos desativados saem da lista e da importação; "
                                            "os dados e o histórico deles continuam no banco")
        self.mostrar_desativados.toggled.connect(lambda _: self.recarregar())
        self.tabela.adicionar_acao(self.mostrar_desativados)
        self.alternar = Botao("Desativar", "secundaria", "eye-off")
        self.alternar.setEnabled(False)
        self.alternar.setVisible(pode)
        self.editar = Botao("Editar", "secundaria", "pencil")
        self.editar.setEnabled(False)
        self.editar.setVisible(pode)
        self.abrir = Botao("Abrir", "secundaria", "arrow-right")
        self.abrir.setEnabled(False)
        self.tabela.adicionar_acao(self.alternar)
        self.tabela.adicionar_acao(self.editar)
        self.tabela.adicionar_acao(self.abrir)
        self.tabela.selecao_alterada.connect(self._ao_selecionar)
        self.alternar.clicked.connect(lambda: self.alternar_ativo(self.tabela.selecao()[0]["_eq"]))
        self.editar.clicked.connect(lambda: self.editar_equipamento(self.tabela.selecao()[0]["_eq"]))
        self.abrir.clicked.connect(lambda: self.abrir_equipamento(self.tabela.selecao()[0]))
        self.tabela.linha_ativada.connect(self.abrir_equipamento)
        self.tabela.setMinimumHeight(420)
        self.corpo.addWidget(self.tabela, 1)

    def recarregar(self) -> None:
        try:
            equipamentos = servico.listar_equipamentos(self.ctx.usuario,
                                                       incluir_inativos=self.mostrar_desativados.isChecked())
            envios = servico.listar_envios(self.ctx.usuario, limite=LIMITE_HISTORICO)
            qualidade = servico.resumo_qualidade(self.ctx.usuario)
        except Exception as erro:  # noqa: BLE001
            self.mostrar_erro(erro, "listar equipamentos")
            return
        from .equipamento import selo_qualidade
        leituras: dict[int, int] = {}
        ultimo: dict[int, object] = {}
        for r in envios:
            leituras[r.equipamento_id] = leituras.get(r.equipamento_id, 0) + r.novas
            ultimo.setdefault(r.equipamento_id, r.recebido_em)
        self.tabela.definir_linhas([
            {"nome": e.nome, "tipo": self.ctx.nome_tipo(e.tipo_sensor), "serie": e.numero_serie, "local": e.local,
             "criado": e.criado_em, "leituras": leituras.get(e.id, 0), "ultimo": ultimo.get(e.id),
             "qualidade": selo_qualidade(qualidade.get(e.id)),
             "situacao": "Ativo" if e.ativo else "Desativado", "_eq": e}
            for e in equipamentos])
        self._ao_selecionar(self.tabela.selecao())

    def _ao_selecionar(self, selecao) -> None:
        um = len(selecao) == 1
        for b in (self.editar, self.abrir, self.alternar):
            b.setEnabled(um)
        ativo = not um or selecao[0]["_eq"].ativo
        self.alternar.setText(" Desativar" if ativo else " Reativar")
        self.alternar.definir_icone("eye-off" if ativo else "eye")

    def alternar_ativo(self, eq: Equipamento, confirmar: bool = True) -> Equipamento | None:
        novo = alternar_equipamento(self, self.ctx, eq, confirmar)
        if novo is not None:
            self._salvo(f"Equipamento {eq.nome} {'reativado' if novo.ativo else 'desativado'}.")
        return novo

    def abrir_equipamento(self, linha: dict):
        """Abre a página do equipamento (abas do plugin + abas comuns)."""
        try:
            return self.ctx.abrir_equipamento(linha["_eq"].id)
        except Exception as erro:  # noqa: BLE001
            self.mostrar_erro(erro, "abrir equipamento")
            return None

    def novo_equipamento(self) -> "DialogoEquipamento":
        d = DialogoEquipamento(self.ctx, None, self.window())
        d.accepted.connect(lambda: self._salvo(f"Equipamento {d.resultado.nome} cadastrado."))
        d.open()
        return d

    def editar_equipamento(self, eq: Equipamento) -> "DialogoEquipamento | None":
        if not self.ctx.pode("cadastro"):
            return None
        d = DialogoEquipamento(self.ctx, eq, self.window())
        d.accepted.connect(lambda: self._salvo(f"Equipamento {d.resultado.nome} atualizado."))
        d.open()
        return d

    def _salvo(self, texto: str) -> None:
        self.ctx.dados_alterados.emit("equipamentos")
        self.mostrar_aviso(texto, "sucesso")


def alternar_equipamento(pai: QWidget, ctx, eq: Equipamento, confirmar: bool = True) -> Equipamento | None:
    """Desativa (com confirmação) ou reativa o equipamento. Devolve o equipamento
    atualizado, ou None se a pessoa desistiu ou deu erro (o erro vai para o aviso de `pai`)."""
    if eq.ativo and confirmar and not DialogoConfirmacao.perguntar(
            pai.window(), f"Desativar {eq.nome}?",
            "O equipamento sai da lista de equipamentos e da importação. As leituras, os envios e o "
            "histórico continuam no banco e podem ser exportados. Você pode reativá-lo depois "
            "(marque “Mostrar desativados” na lista).", "Desativar equipamento", destrutivo=True):
        return None
    try:
        return servico.alterar_equipamento(ctx.usuario, eq.id, ativo=not eq.ativo)
    except Exception as erro:  # noqa: BLE001
        texto = ctx.tratar_erro(erro, "desativar/reativar equipamento")
        if hasattr(pai, "aviso"):
            pai.aviso.mostrar(texto, "erro")
        return None


class DialogoEquipamento(DialogoFormulario):
    """Criar (eq=None) ou editar. O tipo de sensor não muda depois de criado.
    Além dos campos comuns, o formulário traz a ficha do plugin do tipo
    (gerada a partir dela); a validação é do backend, e os erros voltam para
    o campo de cada um."""

    def __init__(self, ctx, eq: Equipamento | None = None, parent=None):
        novo = eq is None
        super().__init__("Novo equipamento" if novo else f"Editar {eq.nome}",
                         "Cada unidade física é um equipamento. Quem importa dados escolhe o equipamento, "
                         "então use um nome fácil de reconhecer." if novo else
                         "O tipo de sensor não muda depois do cadastro.",
                         "Cadastrar" if novo else "Salvar", parent)
        self.ctx = ctx
        self.eq = eq
        # duas colunas: dados gerais à esquerda; instalação e ficha do sensor à direita
        coluna_geral, self._coluna_ficha = self.colunas("Identificação", "Localização")
        self.ajuda_como_dica = True
        self.form = coluna_geral
        self.tipo = QComboBox()
        for t in ctx.tipos_sensor():
            self.tipo.addItem(t.nome, t.codigo)
        self.campo("Tipo de sensor", self.tipo)
        self.nome = self.campo("Nome", QLineEdit(), "Único no laboratório. Ex.: Pluviômetro telhado.")
        self.nome.setPlaceholderText("ex.: Pluviômetro 1")
        self.observacoes = QPlainTextEdit()
        self.observacoes.setFixedHeight(DIMENSAO["altura_controle"] * 2)
        self.observacoes.setPlaceholderText("opcional")
        self.campo("Observações", self.observacoes)
        self.form = self._coluna_ficha
        self.local = self.campo("Local", QLineEdit())
        self.local.setPlaceholderText("opcional · ex.: bacia experimental, estação 1")
        coordenadas = QWidget()
        linha = QHBoxLayout(coordenadas)
        linha.setContentsMargins(0, 0, 0, 0)
        linha.setSpacing(ESPACO["sm"])
        self.latitude, self.longitude = QLineEdit(), QLineEdit()
        self.latitude.setPlaceholderText("latitude · ex.: -29,7206")
        self.longitude.setPlaceholderText("longitude · ex.: -53,7163")
        self.latitude.setAccessibleName("Latitude")
        self.longitude.setAccessibleName("Longitude")
        linha.addWidget(self.latitude)
        linha.addWidget(self.longitude)
        self.campo("Coordenadas", coordenadas, "Clique no mapa para marcar a posição, ou digite em graus "
                                               "decimais (WGS84). Opcionais.")
        self._erros[self.latitude] = self._erros[coordenadas]
        self._erros[self.longitude] = self._erros[coordenadas]
        # mapa: um clique preenche as coordenadas; digitar move o marcador
        self.mapa = MapaSeletor(zoom=13, carregar_ladrilhos=os.environ.get("HIDROLOG_MAPA_OFFLINE") != "1")
        self.mapa.setFixedHeight(230)
        self.form.addRow(self.mapa)
        self.mapa.posicao_escolhida.connect(self._posicao_do_mapa)
        self.latitude.editingFinished.connect(self._posicao_digitada)
        self.longitude.editingFinished.connect(self._posicao_digitada)
        if not novo:
            self.tipo.setCurrentIndex(max(0, self.tipo.findData(eq.tipo_sensor)))
            self.tipo.setEnabled(False)
            self.nome.setText(eq.nome)
            self.local.setText(eq.local or "")
            for w, v in ((self.latitude, eq.latitude), (self.longitude, eq.longitude)):
                w.setText(f"{v:.6g}".replace(".", ",") if v is not None else "")
            self.mapa.definir_posicao(eq.latitude, eq.longitude)
            self.observacoes.setPlainText(eq.observacoes or "")
        self._respiro_ficha = QWidget()
        self._respiro_ficha.setFixedHeight(ESPACO["md"])
        self.form.addRow(self._respiro_ficha)
        self.titulo_ficha = rotulo("", "titulo_secao")
        self.form.addRow(self.titulo_ficha)
        self.ficha: FormularioFicha | None = None
        self.tipo.currentIndexChanged.connect(self._montar_ficha)
        self._montar_ficha()

    def _posicao_do_mapa(self, lat: float, lon: float) -> None:
        self.latitude.setText(f"{lat:.6f}".replace(".", ","))
        self.longitude.setText(f"{lon:.6f}".replace(".", ","))

    def _posicao_digitada(self) -> None:
        try:
            lat = float(self.latitude.text().strip().replace(",", "."))
            lon = float(self.longitude.text().strip().replace(",", "."))
        except ValueError:
            return          # incompleto ou inválido: o backend aponta o erro ao salvar
        if -90 <= lat <= 90 and -180 <= lon <= 180:
            self.mapa.definir_posicao(lat, lon)

    def _montar_ficha(self, *_):
        if self.ficha is not None:
            self.ficha.remover()
            self.ficha.deleteLater()
        codigo = self.tipo.currentData()
        campos = servico.ficha_do_tipo(codigo) if codigo else []
        # as linhas da ficha entram no mesmo formulário, alinhadas com os campos comuns
        self.ficha = FormularioFicha(campos, self, form=self._coluna_ficha, so_editaveis=True, ajuda_como_dica=True)
        self.ficha.hide()
        self.ficha.definir_valores(self.eq.atributos if self.eq is not None else
                                   {c.chave: c.padrao for c in campos if c.padrao is not None})
        tem_ficha = bool(self.ficha.campos)
        self.titulo_ficha.setText(f"Ficha do {self.tipo.currentText()}" if tem_ficha else "")
        self.titulo_ficha.setVisible(tem_ficha)
        self._respiro_ficha.setVisible(tem_ficha)
        self.adjustSize()

    def validar(self) -> bool:
        if self.tipo.currentData() is None:
            self.aviso.mostrar("Nenhum tipo de sensor está instalado.", "erro")
            return False
        if not self.nome.text().strip():
            self.erro_campo(self.nome, "Informe o nome do equipamento.")
            return False
        return True

    def limpar_erros(self) -> None:
        super().limpar_erros()
        if self.ficha is not None:
            self.ficha.limpar_erros()

    def salvar(self) -> Equipamento:
        u = self.ctx.usuario
        comuns = dict(latitude=self.latitude.text().strip() or None, longitude=self.longitude.text().strip() or None)
        atributos = self.ficha.valores() if self.ficha is not None else {}
        # nº de série, altitude e data de instalação não são pedidos no cadastro
        # (o nº de série é registrado a partir das leituras) e não são alterados aqui
        valores = dict(local=self.local.text().strip() or None,
                       observacoes=self.observacoes.toPlainText().strip() or None)
        if self.eq is None:
            return servico.criar_equipamento(u, self.tipo.currentData(), self.nome.text().strip(), **valores,
                                             **comuns, atributos=atributos)
        # no alterar, string vazia apaga o campo (None = não mexe)
        valores = {k: (v or "") for k, v in valores.items()}
        return servico.alterar_equipamento(u, self.eq.id, nome=self.nome.text().strip(), **valores, **comuns,
                                           atributos=atributos if self.ficha and self.ficha.campos else None)

    def tratar_erro_salvar(self, erro) -> bool:
        if isinstance(erro, Conflito):
            self.erro_campo(self.nome, f"Já existe um equipamento chamado “{self.nome.text().strip()}”.")
            return True
        if isinstance(erro, ErroValidacao):
            comuns = {"nome": self.nome, "latitude": self.latitude, "longitude": self.longitude}
            achou = False
            for chave, mensagem in erro.campos.items():
                texto = acentuar(mensagem)
                if chave in comuns:
                    self.erro_campo(comuns[chave], texto)
                    achou = True
            if self.ficha is not None:
                achou = self.ficha.mostrar_erros({k: acentuar(v) for k, v in erro.campos.items()}) or achou
            return achou
        return False
