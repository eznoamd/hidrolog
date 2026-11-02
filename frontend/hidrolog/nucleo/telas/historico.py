"""Histórico de envios: tabela (quem, quando, equipamento, contagens) e detalhe."""

from __future__ import annotations

from pathlib import PurePath

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QGridLayout, QHBoxLayout, QVBoxLayout

from app import servico
from app.nucleo.tipos import ResumoEnvio
from design.componentes import Botao, Cartao, Coluna, Selo, TabelaFiltravel, formatos, rotulo
from design.tema import DIMENSAO, ESPACO

from ..erros import traduzir_aviso
from .comum import PaginaBase

LIMITE_HISTORICO = 10000

SITUACAO_ENVIO = {
    "ok": ("Concluído", "sucesso"),
    "aviso": ("Com avisos", "alerta"),
    "sem_novas": ("Sem leituras novas", "neutro"),
}
NOMES_TIPO_ENVIO = {"zip": "Arquivo .zip", "rar": "Arquivo .rar", "pasta": "Pasta",
                    "arquivos": "Arquivos soltos", "misto": "Misto"}
NOMES_CANAL = {"local": "Arquivo deste computador", "upload": "Envio pela API"}


def situacao_envio(r: ResumoEnvio) -> str:
    if r.avisos or r.corrompidas:
        return "aviso"
    return "ok" if r.novas else "sem_novas"


def nome_origem(origem: str | None) -> str:
    """'/media/SD/SD_1.zip; /media/x' -> 'SD_1.zip; x' (o caminho inteiro fica na dica)."""
    if not origem:
        return formatos.TRACO
    return "; ".join(PurePath(p.strip().rstrip("/\\")).name or p.strip() for p in origem.split(";"))


def periodo_curto(inicio, fim) -> str:
    if not inicio or not fim:
        return formatos.TRACO
    return formatos.data(inicio) if inicio.date() == fim.date() else f"{formatos.data(inicio)} – {formatos.data(fim)}"


def linha_envio(r: ResumoEnvio) -> dict:
    return {
        "id": r.id, "quando": r.recebido_em, "usuario": r.usuario, "equipamento": r.equipamento,
        "origem": r.origem, "novas": r.novas, "duplicadas": r.duplicadas, "corrompidas": r.corrompidas,
        "ignoradas": r.ignorados, "periodo": periodo_curto(r.inicio, r.fim), "situacao": situacao_envio(r),
        "_envio": r,
    }


def colunas_historico(compacta: bool = False) -> list[Coluna]:
    cols = [
        Coluna("quando", "Enviado em", "data_hora", largura=136),
        Coluna("usuario", "Usuário", "mono", largura=110),
        Coluna("equipamento", "Equipamento", largura=150, estica=compacta),
    ]
    if not compacta:
        cols.append(Coluna("origem", "Origem", "mono", estica=True, formatar=nome_origem,
                           dica="Arquivo ou pasta enviado (passe o mouse para ver o caminho completo)"))
    cols += [
        Coluna("novas", "Novas", "inteiro", dica="Leituras novas gravadas"),
        Coluna("duplicadas", "Dupl.", "inteiro", dica="Leituras duplicadas (já estavam no banco)"),
        Coluna("corrompidas", "Corromp.", "inteiro", dica="Leituras corrompidas (guardadas só para diagnóstico)"),
    ]
    if not compacta:
        cols.append(Coluna("ignoradas", "Ignor.", "inteiro", dica="Arquivos ignorados (não são leituras do sensor)"))
    cols += [
        Coluna("periodo", "Período coberto", "mono"),
        Coluna("situacao", "Situação", "selo", selo=lambda v: SITUACAO_ENVIO[v], largura=150),
    ]
    return cols


class PaginaHistorico(PaginaBase):
    depende_de = ("envios", "equipamentos")

    def __init__(self, ctx):
        super().__init__(ctx, "Histórico de envios",
                         "Quem enviou, quando, de qual equipamento e o que entrou no banco. "
                         "Clique duas vezes num envio para ver o detalhe.")
        self.tabela = TabelaFiltravel(colunas_historico(), texto_busca="Buscar por usuário, equipamento ou origem…",
                                      ordenar_por="quando", decrescente=True, titulo_vazio="Nenhum envio ainda",
                                      descricao_vazio="Os envios aparecem aqui depois da primeira importação.",
                                      icone_vazio="history")
        self.tabela.adicionar_filtro("equipamento", "Todos os equipamentos")
        self.detalhe = Botao("Ver detalhe", "secundaria", "eye")
        self.detalhe.setEnabled(False)
        self.tabela.adicionar_acao(self.detalhe)
        self.tabela.selecao_alterada.connect(lambda s: self.detalhe.setEnabled(len(s) == 1))
        self.detalhe.clicked.connect(lambda: self.abrir_detalhe(self.tabela.selecao()[0]))
        self.tabela.linha_ativada.connect(self.abrir_detalhe)
        self.tabela.setMinimumHeight(420)
        self.corpo.addWidget(self.tabela, 1)

    def recarregar(self) -> None:
        try:
            envios = servico.listar_envios(self.ctx.usuario, limite=LIMITE_HISTORICO)
        except Exception as erro:  # noqa: BLE001
            self.mostrar_erro(erro, "listar envios")
            return
        self.tabela.definir_linhas([linha_envio(r) for r in envios])

    def abrir_detalhe(self, linha: dict) -> DialogoEnvio | None:
        try:
            envio = servico.obter_envio(self.ctx.usuario, linha["id"])
        except Exception as erro:  # noqa: BLE001
            self.mostrar_erro(erro, "detalhe do envio")
            return None
        dialogo = DialogoEnvio(envio, self.ctx, self.window())
        dialogo.open()
        return dialogo


class DialogoEnvio(QDialog):
    """Detalhe de um envio: todas as contagens, período, origem e avisos."""

    def __init__(self, r: ResumoEnvio, ctx, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Envio {r.id}")
        self.setMinimumWidth(DIMENSAO["largura_formulario"] * 2)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(ESPACO["xl"], ESPACO["xl"], ESPACO["xl"], ESPACO["lg"])
        lay.setSpacing(ESPACO["md"])
        topo = QHBoxLayout()
        topo.addWidget(rotulo(f"Envio {r.id} · {r.equipamento}", "titulo"), 1)
        texto, tom = SITUACAO_ENVIO[situacao_envio(r)]
        topo.addWidget(Selo(texto, tom))
        lay.addLayout(topo)
        lay.addWidget(rotulo(f"Enviado por {r.usuario} em {formatos.data_hora(r.recebido_em, segundos=True)}.",
                             "secundario"))

        contagens = Cartao("Leituras")
        g = QGridLayout()
        g.setHorizontalSpacing(ESPACO["xl"])
        g.setVerticalSpacing(ESPACO["xs"])
        for i, (titulo, valor) in enumerate((("Novas", r.novas), ("Duplicadas", r.duplicadas),
                                             ("Corrompidas", r.corrompidas), ("Válidas", r.validas),
                                             ("Lidas", r.leituras))):
            v = rotulo(formatos.inteiro(valor), "metrica_valor")
            g.addWidget(v, 0, i)
            g.addWidget(rotulo(titulo, "rotulo_campo"), 1, i)
        g.setColumnStretch(5, 1)
        contagens.corpo.addLayout(g)
        lay.addWidget(contagens)

        info = Cartao("Envio")
        f = QGridLayout()
        f.setHorizontalSpacing(ESPACO["lg"])
        f.setVerticalSpacing(ESPACO["sm"])
        linhas = [
            ("Tipo de sensor", ctx.nome_tipo(r.tipo_sensor), False),
            ("Período coberto", formatos.periodo(r.inicio, r.fim), True),
            ("Origem", r.origem, True),
            ("Forma", f"{NOMES_TIPO_ENVIO.get(r.tipo, r.tipo)} · {NOMES_CANAL.get(r.canal, r.canal)}", False),
            ("Arquivos recebidos", formatos.inteiro(r.arquivos_recebidos), True),
            ("Arquivos ignorados", formatos.inteiro(r.ignorados), True),
            ("Duração", formatos.numero(r.duracao_s, 1, "s"), True),
        ]
        for i, (titulo, valor, mono) in enumerate(linhas):
            f.addWidget(rotulo(titulo, "rotulo_campo"), i, 0, Qt.AlignmentFlag.AlignTop)
            v = rotulo(valor or formatos.TRACO, None, mono=mono, quebra=True)
            v.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            f.addWidget(v, i, 1)
        f.setColumnStretch(1, 1)
        info.corpo.addLayout(f)
        lay.addWidget(info)

        if r.avisos:
            avisos = Cartao("Avisos")
            for a in r.avisos:
                avisos.corpo.addWidget(rotulo(f"• {traduzir_aviso(a)}", "secundario", quebra=True))
            lay.addWidget(avisos)

        botoes = QHBoxLayout()
        botoes.addStretch(1)
        fechar = Botao("Fechar", "primaria")
        fechar.setDefault(True)
        fechar.clicked.connect(self.accept)
        botoes.addWidget(fechar)
        lay.addLayout(botoes)
