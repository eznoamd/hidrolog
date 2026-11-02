#!/usr/bin/env python3
"""
Catálogo de componentes do design do Hidrolog.

Mostra cada componente de `design.componentes` isolado, com dados fictícios e
genéricos (nenhum sensor, nenhum dado real), nos temas claro e escuro. Serve
para ver e ajustar o visual sem o banco nem o app; as telas completas do app
ficam nas capturas do teste de ponta a ponta do frontend
(`frontend/ferramentas/ponta_a_ponta.py`).

    venv/bin/python catalogo.py                     # abre o catálogo (tema claro)
    venv/bin/python catalogo.py --tema escuro
    QT_QPA_PLATFORM=offscreen venv/bin/python catalogo.py --capturas   # gera capturas/*.png

A marca é a genérica, a menos que HIDROLOG_MARCA_DIR aponte para uma pasta de marca.
"""

from __future__ import annotations

import argparse
import math
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

RAIZ = Path(__file__).resolve().parent
if str(RAIZ.parent) not in sys.path:
    sys.path.insert(0, str(RAIZ.parent))

from matplotlib.figure import Figure  # noqa: E402
from PySide6.QtCore import Qt, QTimer  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication, QGridLayout, QHBoxLayout, QListWidget, QMainWindow, QSplitter, QStackedWidget, QVBoxLayout,
    QWidget,
)

from design.componentes import (  # noqa: E402
    Abas, AreaSoltarArquivo, Avatar, Botao, Carregando, Cartao, CartaoMetrica, Coluna, DialogoConfirmacao, DialogoSenha, Divisoria,
    EstadoVazio, FaixaAviso, FiguraIncorporada, FormularioFicha, JanelaPrincipal, LogoInstituicao, LogoMarca,
    MapaSeletor, MenuUsuario, Pagina, PainelImportacao, ResumoImportacao, Selo, SeletorEquipamentoPeriodo, SeletorPeriodo,
    TabelaFiltravel, TelaLogin, rotulo, selo_perfil,
)
from design.tema import (  # noqa: E402
    ESPACO, aplicar_tema, alternar_tema, carregar_marca_da_instalacao, cor, modo_atual,
)

TAMANHO = (1280, 820)

EQUIPAMENTOS = [
    {"nome": "Estação 1", "tipo": "Pluviômetro", "local": "Bacia experimental", "leituras": 12480,
     "ultima": datetime(2026, 10, 21, 16, 38), "situacao": "Ativo"},
    {"nome": "Estação 2", "tipo": "Pluviômetro", "local": "Campus", "leituras": 7310,
     "ultima": datetime(2026, 10, 27, 9, 0), "situacao": "Ativo"},
    {"nome": "Sonda A", "tipo": "Nível d'água", "local": "Seção de controle", "leituras": 0,
     "ultima": None, "situacao": "Desativado"},
]

FICHA = [
    SimpleNamespace(chave="intervalo_s", rotulo="Intervalo de amostragem", tipo="inteiro", unidade="s",
                    opcoes=(), ajuda="Tempo entre duas leituras.", somente_leitura=False, origem=None, padrao=60),
    SimpleNamespace(chave="resolucao", rotulo="Resolução", tipo="decimal", unidade="mm", opcoes=(),
                    ajuda="", somente_leitura=False, origem=None, padrao=None),
    SimpleNamespace(chave="modelo", rotulo="Modelo", tipo="escolha", unidade="",
                    opcoes=(("a", "Modelo A"), ("b", "Modelo B")), ajuda="", somente_leitura=False,
                    origem=None, padrao=None),
    SimpleNamespace(chave="aquecido", rotulo="Aquecido", tipo="booleano", unidade="", opcoes=(), ajuda="",
                    somente_leitura=False, origem=None, padrao=None),
    SimpleNamespace(chave="firmware", rotulo="Firmware", tipo="texto", unidade="", opcoes=(),
                    ajuda="", somente_leitura=True, origem="leituras", padrao=None),
]


def _grade(*cartoes: QWidget, colunas: int = 2) -> QWidget:
    w = QWidget()
    g = QGridLayout(w)
    g.setContentsMargins(0, 0, 0, 0)
    g.setSpacing(ESPACO["lg"])
    for i, c in enumerate(cartoes):
        g.addWidget(c, i // colunas, i % colunas, Qt.AlignmentFlag.AlignTop)   # cada cartão na sua altura
    return w


def _cartao(titulo: str, *widgets: QWidget, horizontal: bool = False) -> Cartao:
    c = Cartao(titulo)
    lay = QHBoxLayout() if horizontal else QVBoxLayout()
    lay.setSpacing(ESPACO["md"])
    for w in widgets:
        lay.addWidget(w)
    if horizontal:
        lay.addStretch(1)
    c.corpo.addLayout(lay)
    return c


# ----------------------------------------------------------------- seções

def secao_tipografia_cores() -> Pagina:
    p = Pagina("Tipografia e cores", "Papéis de texto e cores semânticas do tema (tokens).")
    textos = _cartao("Tipografia", *(rotulo(f"{papel}: Leituras do equipamento", papel) for papel in (
        "titulo_pagina", "titulo", "subtitulo", "titulo_cartao", None, "secundario", "legenda",
        "rotulo_campo", "titulo_secao", "erro")), rotulo("mono: 12.480 · 49,6 mm/h", None, mono=True))
    amostras = QWidget()
    g = QGridLayout(amostras)
    g.setSpacing(ESPACO["sm"])
    for i, token in enumerate(("primaria", "sucesso", "alerta", "erro", "info", "neutro", "superficie",
                               "superficie_alt", "borda", "texto", "texto_secundario", "texto_terciario")):
        bloco = QWidget()
        bloco.setFixedSize(36, 24)
        bloco.setStyleSheet(f"background: {cor(token)}; border: 1px solid {cor('borda_forte')}; border-radius: 4px;")
        g.addWidget(bloco, i, 0)
        g.addWidget(rotulo(f"{token}  {cor(token)}", "legenda", mono=True), i, 1)
    p.corpo.addWidget(_grade(textos, _cartao("Cores (tema atual)", amostras)))
    return p


def secao_botoes_selos() -> Pagina:
    p = Pagina("Botões e selos")
    botoes = _cartao("Botões", Botao("Primária", "primaria", "check"), Botao("Secundária", "secundaria", "pencil"),
                     Botao("Perigo", "perigo", "trash-2"), Botao("Fantasma", "fantasma", "x"),
                     Botao("Link", "link"), horizontal=True)
    desabilitado = Botao("Desabilitado", "primaria")
    desabilitado.setEnabled(False)
    estados = _cartao("Estados", desabilitado, Botao("Grande", "primaria", "upload", grande=True), horizontal=True)
    selos = _cartao("Selos", *(Selo(t, t) for t in ("neutro", "info", "sucesso", "alerta", "erro")),
                    Selo("sólido", "erro", solido=True), horizontal=True)
    perfis = _cartao("Perfis", *(selo_perfil(p) for p in ("master", "cadastro", "leitura")), horizontal=True)
    p.corpo.addWidget(_grade(botoes, estados, selos, perfis, colunas=1))
    return p


def secao_avisos() -> Pagina:
    p = Pagina("Avisos e estado vazio")
    faixas = _cartao("Faixas de aviso",
                     FaixaAviso("Equipamento cadastrado.", "sucesso", fechavel=True),
                     FaixaAviso("Informação de uma linha.", "info"),
                     FaixaAviso("1 leitura corrompida foi guardada só para diagnóstico. Esta mensagem é longa de "
                                "propósito para quebrar em duas linhas e mostrar o alinhamento do ícone.",
                                "alerta", fechavel=True),
                     FaixaAviso("Senha incorreta. Restam 2 tentativas.", "erro"))
    vazio = EstadoVazio("Nenhum envio ainda", "Importe a pasta do cartão SD para começar.", "inbox",
                        texto_acao="Importar dados", icone_acao="upload")
    p.corpo.addWidget(faixas)
    p.corpo.addWidget(_cartao("Estado vazio", vazio))
    p.corpo.addWidget(_cartao("Carregando", Carregando("Carregando as leituras do período…")))
    menu = MenuUsuario()
    menu.definir_usuario("Ana Souza", "cadastro", "ana")
    p.corpo.addWidget(_cartao("Usuário (avatar e menu da conta)", Avatar("Ana Souza", 40), menu, horizontal=True))
    return p


def secao_metricas() -> Pagina:
    p = Pagina("Cartões de métrica")
    p.corpo.addWidget(_grade(
        CartaoMetrica("Chuva no período", 72.1, "mm", "06/10/2026 – 21/10/2026", nome_icone="cloud-rain"),
        CartaoMetrica("Intensidade máxima", 49.6, "mm/h", "em 08/10/2026 04:14", nome_icone="gauge"),
        CartaoMetrica("Leituras válidas", 10954, "leituras", "1 corrompida guardada", casas=0,
                      nome_icone="database"),
        CartaoMetrica("Alertas abertos", 2, "", "último há 3 dias", casas=0, nome_icone="triangle-alert",
                      selo=("atenção", "alerta")),
        colunas=4))
    return p


def secao_tabela() -> Pagina:
    p = Pagina("Tabela com filtro")
    tabela = TabelaFiltravel([
        Coluna("nome", "Nome", estica=True), Coluna("tipo", "Tipo"), Coluna("local", "Local"),
        Coluna("leituras", "Leituras", "inteiro"), Coluna("ultima", "Última leitura", "data_hora"),
        Coluna("situacao", "Situação", "selo",
               selo=lambda v: (v, "sucesso" if v == "Ativo" else "neutro")),
    ], texto_busca="Buscar equipamento…", ordenar_por="nome")
    tabela.adicionar_filtro("tipo", "Todos os tipos")
    tabela.adicionar_acao(Botao("Novo", "primaria", "plus"))
    tabela.definir_linhas(EQUIPAMENTOS)
    vazia = TabelaFiltravel([Coluna("nome", "Nome", estica=True)], titulo_vazio="Nenhum equipamento",
                            descricao_vazio="Cadastre o primeiro equipamento.", mostrar_busca=False)
    vazia.definir_linhas([])
    p.corpo.addWidget(tabela)
    p.corpo.addWidget(_cartao("Sem linhas", vazia))
    return p


def secao_abas() -> Pagina:
    p = Pagina("Abas", "Abas do plugin, um separador e as abas comuns, como na página do equipamento.")
    abas = Abas()
    for chave, titulo in (("visao", "Visão geral"), ("serie", "Série temporal"), ("eventos", "Eventos")):
        abas.adicionar(chave, titulo, lambda t=titulo: EstadoVazio(t, "Conteúdo criado ao abrir a aba."))
    abas.adicionar_separador()
    for chave, titulo in (("qualidade", "Qualidade"), ("envios", "Envios"), ("cadastro", "Cadastro")):
        abas.adicionar(chave, titulo, lambda t=titulo: EstadoVazio(t, "Aba comum do núcleo."))
    abas.setMinimumHeight(320)
    p.corpo.addWidget(abas)
    return p


def secao_formulario() -> Pagina:
    p = Pagina("Formulário da ficha", "Gerado a partir de uma ficha declarativa; os erros vêm do backend.")
    normal = FormularioFicha(FICHA)
    normal.definir_valores({"intervalo_s": 60, "modelo": "a", "firmware": "2.11.6"})
    com_erro = FormularioFicha(FICHA[:2])
    com_erro.definir_valores({"intervalo_s": 5})
    com_erro.mostrar_erros({"intervalo_s": "Mínimo 10 s."})
    p.corpo.addWidget(_grade(_cartao("Ficha", normal), _cartao("Com erro de validação", com_erro)))
    return p


def secao_periodo() -> Pagina:
    p = Pagina("Seletores de período")
    fim = date(2026, 10, 21)
    p.corpo.addWidget(_cartao("Período", SeletorPeriodo(fim - timedelta(days=15), fim)))
    p.corpo.addWidget(_cartao("Equipamento e período",
                              SeletorEquipamentoPeriodo([(1, "Estação 1"), (2, "Estação 2")],
                                                        fim - timedelta(days=15), fim)))
    return p


def secao_importacao() -> Pagina:
    p = Pagina("Importação")
    area = AreaSoltarArquivo()
    andamento = PainelImportacao()
    andamento.iniciar(1200)
    andamento.atualizar(480, 1200, "Lendo os arquivos…")
    resumo = PainelImportacao()
    resumo.concluir(ResumoImportacao(novas=10955, duplicadas=0, corrompidas=1, ignoradas=2,
                                     inicio=datetime(2026, 10, 6, 11, 13), fim=datetime(2026, 10, 21, 16, 38),
                                     arquivos=10957))
    p.corpo.addWidget(_cartao("Área de soltar arquivo", area))
    p.corpo.addWidget(_grade(_cartao("Em andamento", andamento), _cartao("Concluída", resumo)))
    return p


def secao_mapa() -> Pagina:
    p = Pagina("Mapa", "Clique para marcar a posição; arraste para mover; roda ou +/− para zoom.")
    mapa = MapaSeletor(zoom=11, carregar_ladrilhos=os.environ.get("HIDROLOG_MAPA_OFFLINE") != "1")
    mapa.setFixedHeight(380)
    mapa.definir_posicao(*mapa.centro())
    p.corpo.addWidget(_cartao("Escolha de posição", mapa))
    return p


def secao_grafico() -> Pagina:
    p = Pagina("Gráfico", "Figura do matplotlib com o estilo do tema (dados sintéticos).")
    fig = Figure(figsize=(8, 3.6))
    ax = fig.subplots()
    horas = [i / 4 for i in range(4 * 48)]
    chuva = [max(0.0, 30 * math.exp(-((h - 14) ** 2) / 6) + 8 * math.exp(-((h - 34) ** 2) / 10)) for h in horas]
    ax.plot(horas, chuva, label="intensidade")
    ax.fill_between(horas, chuva, alpha=0.2)
    ax.set_xlabel("Horas")
    ax.set_ylabel("mm/h")
    ax.legend()
    p.corpo.addWidget(FiguraIncorporada(fig, "Série de exemplo", altura_minima=360))
    return p


def secao_marca() -> Pagina:
    p = Pagina("Marca", "Logos da pasta de marca da instalação; sem imagem, o texto LOGO no lugar.")
    p.corpo.addWidget(_grade(_cartao("Logo do laboratório", LogoMarca(altura=72), horizontal=True),
                             _cartao("Logo da instituição", LogoInstituicao(altura=44), horizontal=True)))
    return p


def secao_dialogos(janela: QWidget) -> Pagina:
    p = Pagina("Diálogos")
    confirmar = Botao("Confirmação destrutiva", "perigo", "trash-2")
    confirmar.clicked.connect(lambda: DialogoConfirmacao.perguntar(
        janela, "Desativar equipamento?", "Os dados continuam no banco.", "Desativar", destrutivo=True))
    senha = Botao("Confirmação com senha", "primaria", "lock")
    senha.clicked.connect(lambda: DialogoSenha(
        "Instalar plugin “Exemplo” v0.1.0?", [("Origem", "github.com/lab/plugin-exemplo @ v0.1.0")],
        aviso="Um plugin é um programa: instale apenas plugins de origem confiável.",
        texto_confirmar="Instalar", ao_confirmar=lambda s: None, parent=janela).exec())
    p.corpo.addWidget(_cartao("Abrir", confirmar, senha, horizontal=True))
    return p


def secao_login() -> QWidget:
    return TelaLogin(versao="0.1 (catálogo)")


def janela_exemplo() -> JanelaPrincipal:
    """Shell com navegação genérica, como no app (sem dados)."""
    j = JanelaPrincipal()
    j.adicionar_pagina("inicio", "Início", lambda: EstadoVazio("Início", "Métricas e alertas."), "layout-dashboard",
                       ordem=0)
    j.adicionar_pagina("equipamentos", "Equipamentos", lambda: EstadoVazio("Equipamentos"), "cpu", ordem=1)
    j.adicionar_pagina("importacao", "Importar dados", lambda: EstadoVazio("Importar dados"), "upload", ordem=2)
    j.adicionar_secao("admin", "Administração", ordem=900, recolhivel=False)
    j.adicionar_pagina("usuarios", "Usuários", lambda: EstadoVazio("Usuários"), "users", secao="admin")
    j.definir_usuario("Pessoa de exemplo", "master")
    j.ir_para("inicio")
    return j


SECOES = [
    ("tipografia", "Tipografia e cores", secao_tipografia_cores),
    ("botoes", "Botões e selos", secao_botoes_selos),
    ("avisos", "Avisos e estado vazio", secao_avisos),
    ("metricas", "Cartões de métrica", secao_metricas),
    ("tabela", "Tabela com filtro", secao_tabela),
    ("abas", "Abas", secao_abas),
    ("formulario", "Formulário da ficha", secao_formulario),
    ("periodo", "Seletores de período", secao_periodo),
    ("importacao", "Importação", secao_importacao),
    ("mapa", "Mapa", secao_mapa),
    ("grafico", "Gráfico", secao_grafico),
    ("marca", "Marca", secao_marca),
    ("dialogos", "Diálogos", None),
    ("login", "Tela de login", secao_login),
]


class Catalogo(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Hidrolog · catálogo de componentes")
        self.lista = QListWidget()
        self.lista.setFixedWidth(220)
        self.lista.setSpacing(3)
        self.pilha = QStackedWidget()
        self.chaves: list[str] = []
        for chave, titulo, _ in SECOES:
            self.lista.addItem(titulo)
            self.chaves.append(chave)
            self.pilha.addWidget(QWidget())        # criada ao abrir
        self._criadas: set[str] = set()
        self.lista.currentRowChanged.connect(self.mostrar)
        lado = QWidget()
        v = QVBoxLayout(lado)
        v.setContentsMargins(ESPACO["md"], ESPACO["md"], ESPACO["md"], ESPACO["md"])
        v.addWidget(rotulo("Catálogo", "titulo"))
        v.addWidget(self.lista, 1)
        v.addWidget(Divisoria())
        self.botao_tema = Botao("Alternar tema", "secundaria", "moon")
        self.botao_tema.clicked.connect(self._alternar_tema)
        v.addWidget(self.botao_tema)
        janela = Botao("Abrir janela de exemplo", "link")
        janela.clicked.connect(self._abrir_janela)
        v.addWidget(janela)
        divisor = QSplitter()
        divisor.addWidget(lado)
        divisor.addWidget(self.pilha)
        divisor.setStretchFactor(1, 1)
        self.setCentralWidget(divisor)
        self._janela_exemplo = None
        self.lista.setCurrentRow(0)

    def mostrar(self, linha: int) -> QWidget:
        chave, _, fabrica = SECOES[linha]
        if chave not in self._criadas:
            antigo = self.pilha.widget(linha)
            novo = secao_dialogos(self) if chave == "dialogos" else fabrica()
            if isinstance(novo, Pagina):
                novo.corpo.addStretch(1)       # conteúdo no topo, sem espalhar o espaço livre
            self.pilha.insertWidget(linha, novo)
            self.pilha.removeWidget(antigo)
            antigo.deleteLater()
            self._criadas.add(chave)
        self.pilha.setCurrentIndex(linha)
        return self.pilha.widget(linha)

    def recriar(self) -> None:
        """Recria as seções (ex. depois de trocar o tema, para as cores dos exemplos)."""
        atual = self.lista.currentRow()
        self._criadas.clear()
        for i in range(self.pilha.count()):
            antigo = self.pilha.widget(i)
            self.pilha.insertWidget(i, QWidget())
            self.pilha.removeWidget(antigo)
            antigo.deleteLater()
        self.mostrar(max(0, atual))

    def _alternar_tema(self) -> None:
        alternar_tema(QApplication.instance())
        self.recriar()

    def _abrir_janela(self) -> None:
        self._janela_exemplo = janela_exemplo()
        self._janela_exemplo.resize(*TAMANHO)
        self._janela_exemplo.show()


def _esperar(app, ms: int = 120) -> None:
    fim = datetime.now() + timedelta(milliseconds=ms)
    while datetime.now() < fim:
        app.processEvents()


def gerar_capturas(app, catalogo: Catalogo, pasta: Path, modos=("claro", "escuro")) -> list[Path]:
    pasta.mkdir(parents=True, exist_ok=True)
    salvas = []
    for modo in modos:
        aplicar_tema(app, modo)
        catalogo.recriar()
        for i, (chave, _, _) in enumerate(SECOES):
            catalogo.lista.setCurrentRow(i)
            _esperar(app)
            destino = pasta / f"{i + 1:02d}_{chave}_{modo}.png"
            catalogo.grab().save(str(destino))
            salvas.append(destino)
        janela = janela_exemplo()
        janela.resize(*TAMANHO)
        janela.show()
        _esperar(app)
        destino = pasta / f"{len(SECOES) + 1:02d}_janela_{modo}.png"
        janela.grab().save(str(destino))
        salvas.append(destino)
        janela.close()
    return salvas


def main() -> int:
    ap = argparse.ArgumentParser(description="Catálogo de componentes do Hidrolog")
    ap.add_argument("--tema", choices=("claro", "escuro"), default="claro")
    ap.add_argument("--capturas", action="store_true", help="gera capturas/*.png e sai")
    args = ap.parse_args()
    if os.environ.get("HIDROLOG_MARCA_DIR"):
        carregar_marca_da_instalacao(os.environ["HIDROLOG_MARCA_DIR"])
    app = QApplication(sys.argv)
    aplicar_tema(app, args.tema)
    catalogo = Catalogo()
    catalogo.resize(*TAMANHO)
    catalogo.show()
    if args.capturas:
        os.environ.setdefault("HIDROLOG_MAPA_OFFLINE", "1")
        salvas = gerar_capturas(app, catalogo, RAIZ / "capturas")
        print(f"{len(salvas)} capturas em {RAIZ / 'capturas'}")
        return 0
    QTimer.singleShot(0, lambda: catalogo.setWindowTitle(f"{catalogo.windowTitle()} · tema {modo_atual()}"))
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
