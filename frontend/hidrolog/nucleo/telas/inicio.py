"""Início: métricas gerais, atalhos e os últimos envios."""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout

from app import servico
from design.componentes import Botao, Cartao, CartaoMetrica, Coluna, TabelaFiltravel, formatos, rotulo
from design.tema import DIMENSAO, ESPACO

from .comum import PaginaBase, grade_metricas
from .historico import LIMITE_HISTORICO, colunas_historico, linha_envio

ULTIMOS = 5
ALTURA_VAZIO = 220   # tabela sem linhas: espaço para o EstadoVazio


def altura_tabela(linhas: int) -> int:
    """Altura de uma TabelaFiltravel embutida sem busca: cabeçalho + linhas."""
    if linhas == 0:
        return ALTURA_VAZIO
    return (linhas + 1) * DIMENSAO["altura_linha_tabela"] + 2 * DIMENSAO["borda_foco"] + ESPACO["sm"] + 2


class PaginaInicio(PaginaBase):
    depende_de = ("envios", "equipamentos", "qualidade")

    def __init__(self, ctx):
        super().__init__(ctx, "Início", "Resumo do banco de dados do laboratório.")
        self.c_equip = CartaoMetrica("Equipamentos ativos", None, "", casas=0, nome_icone="cpu")
        self.c_envios = CartaoMetrica("Envios", None, "envios", casas=0, nome_icone="history")
        self.c_leituras = CartaoMetrica("Leituras no banco", None, "leituras", casas=0, nome_icone="database")
        self.c_ultimo = CartaoMetrica("Último envio", None, "", nome_icone="upload")
        self.corpo.addLayout(grade_metricas([self.c_equip, self.c_envios, self.c_leituras, self.c_ultimo]))

        self.alertas = Cartao("Alertas de qualidade")
        self.alertas.corpo.addWidget(rotulo("Equipamentos com ocorrências abertas nas regras de qualidade. Clique duas "
                                            "vezes para abrir a aba Qualidade.", "secundario", quebra=True))
        self.tabela_alertas = TabelaFiltravel([
            Coluna("nome", "Equipamento", largura=200), Coluna("tipo", "Tipo", largura=170),
            Coluna("selo", "Qualidade", "selo", selo=lambda v: v, largura=140),
            Coluna("alertas", "Alertas", "inteiro"), Coluna("suspeitas", "Suspeitas", "inteiro"),
            Coluna("avisos", "Avisos", "inteiro"), Coluna("vazio", "", estica=True, formatar=lambda _: "")],
            mostrar_busca=False, embutida=True, titulo_vazio="Nenhum alerta", icone_vazio="circle-check")
        self.tabela_alertas.contagem.hide()
        self.tabela_alertas.linha_ativada.connect(self._abrir_qualidade)
        self.alertas.corpo.addWidget(self.tabela_alertas)
        self.corpo.addWidget(self.alertas)

        atalhos = Cartao("Atalhos")
        linha = QHBoxLayout()
        botoes = []
        if ctx.pode("cadastro"):
            botoes.append(("Importar dados", "primaria", "upload", "importacao"))
        botoes += [("Exportar dados", "secundaria", "download", "exportacao"),
                   ("Histórico de envios", "secundaria", "history", "historico"),
                   ("Equipamentos", "secundaria", "cpu", "equipamentos")]
        self.atalhos: dict[str, Botao] = {}
        for texto, variante, ic, chave in botoes:
            b = Botao(texto, variante, ic)
            b.clicked.connect(lambda _=False, c=chave: ctx.ir_para(c))
            linha.addWidget(b)
            self.atalhos[chave] = b
        linha.addStretch(1)
        atalhos.corpo.addLayout(linha)
        self.corpo.addWidget(atalhos)

        cartao = Cartao("Últimos envios")
        ver = Botao("Ver histórico", "link")
        ver.clicked.connect(lambda: ctx.ir_para("historico"))
        cartao.cabecalho.addWidget(ver)
        self.ultimos = TabelaFiltravel(colunas_historico(compacta=True), mostrar_busca=False, ordenar_por="quando",
                                       decrescente=True, embutida=True, titulo_vazio="Nenhum envio ainda",
                                       descricao_vazio="Importe os dados de um equipamento para começar.",
                                       icone_vazio="history")
        self.ultimos.contagem.hide()
        cartao.corpo.addWidget(self.ultimos)
        self.corpo.addWidget(cartao)

        eq = Cartao("Equipamentos")
        self.equipamentos = TabelaFiltravel([
            Coluna("nome", "Nome", largura=170), Coluna("tipo", "Tipo", largura=170),
            Coluna("serie", "Nº de série", "mono"), Coluna("local", "Local", estica=True),
            Coluna("ultimo", "Último envio", "data_hora"),
            Coluna("ativo", "Situação", "selo", selo=lambda v: ("Ativo", "sucesso") if v else ("Desativado", "neutro"),
                   largura=120)],
            mostrar_busca=False, embutida=True, titulo_vazio="Nenhum equipamento cadastrado",
            descricao_vazio="Cadastre um equipamento na página Equipamentos.", icone_vazio="cpu")
        self.equipamentos.contagem.hide()
        self.equipamentos.linha_ativada.connect(lambda linha: ctx.abrir_equipamento(linha["_eq"].id))
        eq.corpo.addWidget(self.equipamentos)
        self.corpo.addWidget(eq)
        self.corpo.addStretch(1)

    def _abrir_qualidade(self, linha: dict) -> None:
        pagina = self.ctx.abrir_equipamento(linha["_eq"].id)
        if pagina is not None:
            pagina.abas.ir_para("qualidade")

    def recarregar(self) -> None:
        try:
            equipamentos = servico.listar_equipamentos(self.ctx.usuario, incluir_inativos=True)
            envios = servico.listar_envios(self.ctx.usuario, limite=LIMITE_HISTORICO)
        except Exception as erro:  # noqa: BLE001
            self.mostrar_erro(erro, "início")
            return
        try:
            qualidade = servico.resumo_qualidade(self.ctx.usuario)
        except Exception as erro:  # noqa: BLE001
            self.mostrar_erro(erro, "qualidade")
            qualidade = {}
        from .equipamento import selo_qualidade

        por_id = {e.id: e for e in equipamentos}
        com_alerta = sorted((q for q in qualidade.values() if q.total and q.equipamento_id in por_id),
                            key=lambda q: (-q.alertas, -q.suspeitas, -q.avisos))
        self.tabela_alertas.definir_linhas([
            {"nome": por_id[q.equipamento_id].nome, "tipo": self.ctx.nome_tipo(por_id[q.equipamento_id].tipo_sensor),
             "selo": selo_qualidade(q), "alertas": q.alertas, "suspeitas": q.suspeitas, "avisos": q.avisos,
             "vazio": "", "_eq": por_id[q.equipamento_id]} for q in com_alerta])
        self.tabela_alertas.setFixedHeight(altura_tabela(len(com_alerta)))
        self.alertas.setVisible(bool(com_alerta))
        ativos = [e for e in equipamentos if e.ativo]
        tipos = {e.tipo_sensor for e in ativos}
        self.c_equip.definir_valor(len(ativos), f"de {len(equipamentos)}",
                                   f"{len(tipos)} tipo(s) de sensor" if ativos else "nenhum cadastrado")
        self.c_envios.definir_valor(len(envios), descricao=(
            f"{formatos.inteiro(sum(r.duplicadas for r in envios))} leituras duplicadas reconhecidas"
            if envios else "nenhuma importação ainda"))
        try:
            total = sum(servico.resumo_leituras(self.ctx.usuario, e.id).leituras for e in equipamentos)
        except Exception as erro:  # noqa: BLE001
            self.mostrar_erro(erro, "leituras")
            total = sum(r.novas for r in envios)
        self.c_leituras.definir_valor(total, descricao=(
            "todas as estações, contadas nas tabelas dos sensores" if envios else "nenhuma leitura ainda"))
        if envios:
            r = envios[0]
            self.c_ultimo.definir_valor(formatos.data_hora(r.recebido_em), descricao=f"{r.usuario} · {r.equipamento}")
        else:
            self.c_ultimo.definir_valor(None, descricao="nenhum envio ainda")
        self.ultimos.definir_linhas([linha_envio(r) for r in envios[:ULTIMOS]])
        self.ultimos.setFixedHeight(altura_tabela(min(len(envios), ULTIMOS)))
        ultimo_por_eq: dict[int, object] = {}
        for r in envios:
            ultimo_por_eq.setdefault(r.equipamento_id, r.recebido_em)
        self.equipamentos.definir_linhas([
            {"nome": e.nome, "tipo": self.ctx.nome_tipo(e.tipo_sensor), "serie": e.numero_serie, "local": e.local,
             "ultimo": ultimo_por_eq.get(e.id), "ativo": e.ativo, "_eq": e} for e in equipamentos])
        self.equipamentos.setFixedHeight(altura_tabela(len(equipamentos)))
