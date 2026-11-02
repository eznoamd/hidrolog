"""Configurações (só master): gerenciador de plugins e auditoria.

Aba Plugins: os plugins de sensor (ativos, desativados, incompatíveis, com
falha, conflitos, instalados aguardando reinício), importar de uma pasta, de
um .zip ou de um repositório do GitHub (URL + versão), desativar, reativar,
voltar versão e a lista de repositórios confiáveis. Toda ação pede
confirmação e a senha do master, conferida de novo no backend (3 senhas
erradas cancelam). Um plugin novo só entra depois de reiniciar o Hidrolog.

Aba Auditoria: o que foi feito, por quem, quando e com que resultado.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QComboBox, QDialog, QHBoxLayout, QLineEdit, QMenu, QVBoxLayout, QWidget,
)

from app import servico
from design.componentes import (
    Abas, Botao, Cartao, Coluna, DialogoArquivoOuPasta, DialogoSenha, FaixaAviso, SobreposicaoCarregamento,
    TabelaFiltravel, formatos, rotulo,
)
from design.tema import ESPACO

from .. import erros, tarefas
from .comum import DialogoFormulario, PaginaBase

ESTADOS = {
    "ativo": ("Ativo", "sucesso"),
    "desativado": ("Desativado", "neutro"),
    "incompativel": ("Incompatível", "erro"),
    "com falha": ("Com falha", "erro"),
    "conflito": ("Conflito", "alerta"),
    "instalado": ("Reinicie", "info"),
}
ORIGENS = {"interno": "Interno", "pasta": "Pasta", "zip": "Arquivo .zip", "github": "GitHub",
           "registro": "Registrado no código"}
ACOES = {"importar": "Importar", "atualizar": "Atualizar", "desativar": "Desativar", "reativar": "Reativar",
         "voltar_versao": "Voltar versão", "remover": "Remover", "migrar": "Migrar banco",
         "lista_confiavel": "Lista confiável"}
RESULTADOS = {"ok": ("Concluído", "sucesso"), "recusado": ("Recusado", "alerta"),
              "cancelado": ("Cancelado", "erro"), "erro": ("Erro", "erro")}
AVISO_PROGRAMA = ("Um plugin é um programa: ele roda com acesso ao banco e aos arquivos deste computador. "
                  "Instale apenas plugins de origem confiável.")


def texto_origem(p) -> str:
    if p.origem == "github" and p.url:
        return f"{p.url.removeprefix('https://')} @ {p.tag}" if p.tag else p.url.removeprefix("https://")
    return ORIGENS.get(p.origem, p.origem)


def hash_curto(sha: str) -> str:
    return f"{sha[:4]}…{sha[-4:]}" if sha and len(sha) > 12 else (sha or formatos.TRACO)


def colunas_plugins() -> list[Coluna]:
    return [
        Coluna("nome", "Plugin", largura=200),
        Coluna("codigo", "Código", "mono", largura=100),
        Coluna("versao", "Versão", "mono", largura=72),
        Coluna("contrato", "Contrato", "mono", largura=78),
        Coluna("origem", "Origem", largura=230),
        Coluna("estado", "Situação", "selo", selo=lambda v: ESTADOS.get(v, (v, "neutro")), largura=120),
        Coluna("detalhes", "Detalhes", estica=True),
    ]


def colunas_auditoria() -> list[Coluna]:
    return [
        Coluna("quando", "Quando", "data_hora", largura=136),
        Coluna("login", "Quem", largura=110),
        Coluna("acao", "Ação", largura=120),
        Coluna("plugin", "Plugin", "mono", largura=140),
        Coluna("resultado", "Resultado", "selo", selo=lambda v: RESULTADOS.get(v, (v, "neutro")), largura=110),
        Coluna("detalhes", "Detalhes", estica=True),
    ]


class DialogoGithub(DialogoFormulario):
    """URL do repositório + versão (tag ou release). Nunca "o que estiver no branch"."""

    def __init__(self, parent=None):
        super().__init__("Importar do GitHub",
                         "Informe o repositório e a versão publicada (tag ou release). O app baixa o .zip "
                         "daquela versão, então o código instalado não muda sozinho.", "Continuar", parent)
        self.url = self.campo("Repositório", QLineEdit(), "Ex.: https://github.com/laboratorio/plugin-pluvio")
        self.url.setPlaceholderText("https://github.com/<dono>/<repositório>")
        self.tag = self.campo("Versão (tag)", QLineEdit(), "Ex.: v0.1.0")
        self.tag.setPlaceholderText("v0.1.0")

    def validar(self) -> bool:
        ok = True
        if "github.com/" not in self.url.text():
            self.erro_campo(self.url, "Use a URL de um repositório do GitHub.")
            ok = False
        if not self.tag.text().strip():
            self.erro_campo(self.tag, "Informe a tag ou release.")
            ok = False
        return ok

    def salvar(self):
        return self.url.text().strip(), self.tag.text().strip()


class AbaPlugins(QWidget):
    def __init__(self, pagina: "PaginaConfiguracoes"):
        super().__init__()
        self.pagina = pagina
        self.ctx = pagina.ctx
        self.tarefa: tarefas.Tarefa | None = None
        self.dialogo: QDialog | None = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(ESPACO["lg"])
        self.reiniciar = FaixaAviso("", "info")
        lay.addWidget(self.reiniciar)

        cartao = Cartao("Plugins de sensor")
        cartao.corpo.addWidget(rotulo(
            "Cada tipo de sensor é um plugin. Os plugins são lidos na abertura do app: um plugin com "
            "contrato incompatível ou com falha não é carregado, e os dados dele continuam no banco. "
            "Importar, atualizar, desativar e voltar versão pedem a senha do master e ficam na auditoria.",
            "secundario", quebra=True))
        self.tabela = TabelaFiltravel(colunas_plugins(), mostrar_busca=False, embutida=True,
                                      titulo_vazio="Nenhum plugin instalado", icone_vazio="layers")
        self.tabela.setMinimumHeight(250)
        self.preparando = SobreposicaoCarregamento(self.tabela)
        self.importar = Botao("Importar plugin", "primaria", "plus")
        menu = QMenu(self.importar)
        menu.addAction("Do computador (pasta ou .zip)…", lambda: self.importar_de("computador"))
        menu.addAction("Repositório do GitHub…", lambda: self.importar_de("github"))
        self.importar.setMenu(menu)
        self.alternar = Botao("Desativar", "secundaria", "eye-off")
        self.voltar = Botao("Voltar versão", "secundaria", "history")
        for b in (self.voltar, self.alternar):
            b.setEnabled(False)
            self.tabela.adicionar_acao(b)
        self.tabela.adicionar_acao(self.importar)
        self.alternar.clicked.connect(lambda: self.alternar_ativo(self._selecionado()))
        self.voltar.clicked.connect(lambda: self.voltar_versao(self._selecionado()))
        self.tabela.selecao_alterada.connect(self._ao_selecionar)
        cartao.corpo.addWidget(self.tabela)
        lay.addWidget(cartao)

        confiaveis = Cartao("Repositórios confiáveis do GitHub")
        confiaveis.corpo.addWidget(rotulo(
            "Opcional. Vazia, aceita qualquer repositório (sempre com o aviso, a confirmação e a senha). "
            "Preenchida, só aceita os repositórios ou organizações da lista, separados por vírgula.",
            "secundario", quebra=True))
        linha = QHBoxLayout()
        self.lista_confiavel = QLineEdit()
        self.lista_confiavel.setPlaceholderText("desligada · ex.: laboratorio, outra-org/plugin-x")
        self.lista_confiavel.setAccessibleName("Repositórios confiáveis")
        linha.addWidget(self.lista_confiavel, 1)
        self.salvar_lista = Botao("Salvar lista", "secundaria", "save")
        self.salvar_lista.clicked.connect(self.salvar_confiaveis)
        linha.addWidget(self.salvar_lista)
        confiaveis.corpo.addLayout(linha)
        lay.addWidget(confiaveis)
        lay.addStretch(1)

    # ------------------------------------------------------------------ dados
    def recarregar(self) -> None:
        u = self.ctx.usuario
        infos = servico.listar_plugins(u)
        linhas = []
        for p in infos:
            partes = [p.motivo] if p.motivo else []
            if p.pendente:
                partes.append(erros.acentuar(p.pendente))
            if p.sha256:
                partes.append(f"SHA-256 {hash_curto(p.sha256)}")
            if p.instalado_em and p.origem != "interno":
                partes.append(f"instalado em {formatos.data_hora(p.instalado_em)}"
                              + (f" por {p.instalado_por}" if p.instalado_por else ""))
            if len(p.versoes) > 1:
                partes.append(f"versões guardadas: {', '.join(p.versoes)}")
            linhas.append({"nome": p.nome, "codigo": p.codigo, "versao": p.versao, "contrato": p.contrato,
                           "origem": texto_origem(p), "estado": p.estado,
                           "detalhes": " · ".join(x for x in partes if x) or formatos.TRACO, "_info": p})
        self.tabela.definir_linhas(linhas)
        pendentes = [p for p in infos if p.pendente]
        if pendentes:
            self.reiniciar.mostrar("Reinicie o Hidrolog para aplicar as mudanças nos plugins: "
                                   + "; ".join(f"{p.nome} ({erros.acentuar(p.pendente).rstrip('.')})"
                                               for p in pendentes) + ".", "info")
        else:
            self.reiniciar.limpar()
        self.lista_confiavel.setText(", ".join(c.removeprefix("https://github.com/")
                                               for c in servico.github_confiaveis(u)))
        self._ao_selecionar(self.tabela.selecao())

    def _selecionado(self):
        sel = self.tabela.selecao()
        return sel[0]["_info"] if sel else None

    def _ao_selecionar(self, sel) -> None:
        info = sel[0]["_info"] if sel else None
        pode = info is not None and info.estado != "conflito" and info.origem != "registro"
        self.alternar.setEnabled(pode)
        desativado = info is not None and (info.estado == "desativado" or info.pendente == "desativado")
        self.alternar.setText(" Reativar" if desativado else " Desativar")
        self.alternar.definir_icone("eye" if desativado else "eye-off")
        self.voltar.setEnabled(pode and len(info.versoes) > 1)

    # ------------------------------------------------------------------ importar
    def escolher_local(self) -> str | None:
        """Pasta do plugin ou o pacote .zip, num diálogo só."""
        return DialogoArquivoOuPasta.escolher(self, (".zip",), titulo="Escolher o plugin (pasta ou .zip)",
                                              rotulo_filtro="Pastas e pacotes de plugin")

    def pedir_github(self) -> tuple[str, str] | None:
        d = DialogoGithub(self.window())
        return d.resultado if d.exec() == QDialog.DialogCode.Accepted else None

    def importar_de(self, origem: str) -> None:
        argumentos: dict = {}
        if origem == "computador":
            caminho = self.escolher_local()
            if not caminho:
                return
            origem = "pasta" if Path(caminho).is_dir() else "zip"
            argumentos["caminho"] = caminho
        else:
            resposta = self.pedir_github()
            if not resposta:
                return
            argumentos["url"], argumentos["tag"] = resposta
        self.preparando.mostrar("Preparando o plugin (copiando e conferindo, sem executar nada dele)…")
        self.importar.setEnabled(False)
        self.tarefa = tarefas.executar(self._preparar, origem, argumentos, ao_concluir=self.confirmar_instalacao,
                                       ao_falhar=self._falhou_preparar, nome="preparar plugin")

    def _preparar(self, origem: str, argumentos: dict):
        return servico.preparar_plugin(self.ctx.usuario, origem, **argumentos)

    def _falhou_preparar(self, erro) -> None:
        self.preparando.esconder()
        self.importar.setEnabled(True)
        self.pagina.mostrar_erro(erro, "preparar plugin")
        self._recarregar_auditoria()

    def confirmar_instalacao(self, pacote) -> DialogoSenha:
        self.preparando.esconder()
        self.importar.setEnabled(True)
        verbo = "Atualizar" if pacote.atualizacao else "Instalar"
        titulo = (f"Atualizar “{pacote.nome}” de v{pacote.versao_atual} para v{pacote.versao}?"
                  if pacote.atualizacao and pacote.versao_atual else f"Instalar plugin “{pacote.nome}” v{pacote.versao}?")
        detalhes = [
            ("Origem", pacote.origem_legivel),
            ("Autor", pacote.autor or formatos.TRACO),
            ("Contrato", pacote.contrato),
            ("SHA-256", pacote.sha256),
            ("Cria as tabelas", ", ".join(pacote.tabelas) or formatos.TRACO),
            ("Acrescenta ao cadastro", ", ".join(pacote.cadastro) or formatos.TRACO),
        ]
        if pacote.requer:
            detalhes.append(("Usa do app", ", ".join(pacote.requer)))
        aviso = " ".join([AVISO_PROGRAMA] + [erros.acentuar(a) for a in pacote.avisos])
        u = self.ctx.usuario
        d = DialogoSenha(titulo, detalhes, pacote.descricao, aviso, verbo,
                         ao_confirmar=lambda senha: servico.instalar_plugin(u, pacote.token, senha),
                         mensagem_erro=lambda e: self.ctx.tratar_erro(e, "instalar plugin"), parent=self.window())
        d.finished.connect(lambda codigo: self._fim_instalacao(d, pacote, codigo))
        self.dialogo = d
        d.open()
        return d

    def _fim_instalacao(self, d: DialogoSenha, pacote, codigo: int) -> None:
        if codigo == QDialog.DialogCode.Accepted:
            self.pagina.mostrar_aviso(erros.acentuar(d.resultado), "sucesso")
        elif d.erro_final is not None:
            self.pagina.aviso.mostrar(self.ctx.tratar_erro(d.erro_final, "instalar plugin"), "erro")
        else:
            servico.cancelar_plugin(self.ctx.usuario, pacote.token)
            self.pagina.aviso.mostrar("Importação cancelada: nada foi instalado.", "info")
        self.pagina.recarregar()

    # ------------------------------------------------------------------ ações com senha
    def _pedir_senha(self, titulo, mensagem, verbo, acao, destrutivo=False) -> DialogoSenha:
        d = DialogoSenha(titulo, mensagem=mensagem, texto_confirmar=verbo, ao_confirmar=acao,
                         mensagem_erro=lambda e: self.ctx.tratar_erro(e, titulo), destrutivo=destrutivo,
                         parent=self.window())

        def fim(codigo):
            if codigo == QDialog.DialogCode.Accepted:
                self.pagina.mostrar_aviso(erros.acentuar(d.resultado) if isinstance(d.resultado, str)
                                          else "Feito.", "sucesso")
            elif d.erro_final is not None:
                self.pagina.aviso.mostrar(self.ctx.tratar_erro(d.erro_final, titulo), "erro")
            self.pagina.recarregar()

        d.finished.connect(fim)
        self.dialogo = d
        d.open()
        return d

    def alternar_ativo(self, info) -> DialogoSenha | None:
        if info is None:
            return None
        u = self.ctx.usuario
        if info.estado == "desativado" or info.pendente == "desativado":
            return self._pedir_senha(f"Reativar {info.nome}?", "O plugin volta a carregar na próxima abertura do "
                                     "Hidrolog.", "Reativar",
                                     lambda senha: servico.reativar_plugin(u, info.codigo, senha))
        return self._pedir_senha(
            f"Desativar {info.nome}?",
            "O plugin deixa de carregar na próxima abertura do Hidrolog. Os dados dele continuam no banco e os "
            "equipamentos desse tipo aparecem com as abas comuns e a exportação genérica. Você pode reativar depois.",
            "Desativar", lambda senha: servico.desativar_plugin(u, info.codigo, senha), destrutivo=True)

    def voltar_versao(self, info, versao: str | None = None) -> DialogoSenha | None:
        if info is None:
            return None
        outras = [v for v in info.versoes if v != info.versao]
        if not outras:
            return None
        if versao is None:
            versao = self._escolher_versao(info, outras)
            if versao is None:
                return None
        u = self.ctx.usuario
        return self._pedir_senha(
            f"Voltar {info.nome} para a versão {versao}?",
            f"A versão {versao} fica ativa na próxima abertura do Hidrolog. Se a versão atual já mudou o banco "
            "(migrações que a outra não conhece), a volta é recusada e o backup feito antes da migração é indicado.",
            "Voltar versão", lambda senha: servico.voltar_versao_plugin(u, info.codigo, versao, senha))

    def _escolher_versao(self, info, outras: list[str]) -> str | None:
        d = QDialog(self.window())
        d.setWindowTitle("Voltar versão")
        lay = QVBoxLayout(d)
        lay.setContentsMargins(ESPACO["xl"], ESPACO["xl"], ESPACO["xl"], ESPACO["lg"])
        lay.addWidget(rotulo(f"Versão de {info.nome} a ativar", "subtitulo"))
        combo = QComboBox()
        combo.addItems(list(reversed(outras)))
        lay.addWidget(combo)
        botoes = QHBoxLayout()
        botoes.addStretch(1)
        cancelar, ok = Botao("Cancelar", "secundaria"), Botao("Continuar", "primaria")
        cancelar.clicked.connect(d.reject)
        ok.clicked.connect(d.accept)
        botoes.addWidget(cancelar)
        botoes.addWidget(ok)
        lay.addLayout(botoes)
        return combo.currentText() if d.exec() == QDialog.DialogCode.Accepted else None

    def salvar_confiaveis(self) -> DialogoSenha:
        lista = [x.strip() for x in self.lista_confiavel.text().split(",") if x.strip()]
        u = self.ctx.usuario
        texto = ", ".join(lista) if lista else "nenhum (qualquer repositório)"
        return self._pedir_senha("Alterar a lista de repositórios confiáveis?", f"Lista nova: {texto}.", "Salvar",
                                 lambda senha: servico.definir_github_confiaveis(u, lista, senha) and
                                 "Lista de repositórios confiáveis salva." or
                                 "Lista confiável desligada: qualquer repositório, com aviso e senha.")

    def _recarregar_auditoria(self) -> None:
        self.pagina.auditoria.recarregar()


class AbaAuditoria(QWidget):
    def __init__(self, pagina: "PaginaConfiguracoes"):
        super().__init__()
        self.pagina = pagina
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        cartao = Cartao("Auditoria dos plugins")
        cartao.corpo.addWidget(rotulo("Cada importação, atualização, desativação, volta de versão, senha errada e "
                                      "migração de plugin, com quem fez e o resultado.", "secundario", quebra=True))
        self.tabela = TabelaFiltravel(colunas_auditoria(), texto_busca="Buscar por plugin, pessoa ou detalhe…",
                                      ordenar_por="quando", decrescente=True, embutida=True,
                                      titulo_vazio="Nada registrado ainda", icone_vazio="history")
        self.tabela.adicionar_filtro("acao", "Todas as ações")
        self.tabela.setMinimumHeight(420)
        cartao.corpo.addWidget(self.tabela)
        lay.addWidget(cartao)
        lay.addStretch(1)

    def recarregar(self) -> None:
        registros = servico.listar_auditoria_plugins(self.pagina.ctx.usuario, limite=500)
        self.tabela.definir_linhas([
            {"quando": a.quando, "login": a.login, "acao": ACOES.get(a.acao, a.acao),
             "plugin": " ".join(x for x in (a.codigo, a.versao) if x) or formatos.TRACO,
             "resultado": a.resultado, "detalhes": erros.acentuar(a.detalhes) if a.detalhes else formatos.TRACO}
            for a in registros])


class PaginaConfiguracoes(PaginaBase):
    def __init__(self, ctx):
        super().__init__(ctx, "Configurações", "Plugins de sensor e auditoria (só master).")
        self.abas = Abas()
        self.plugins = AbaPlugins(self)
        self.auditoria = AbaAuditoria(self)
        self.abas.adicionar("plugins", "Plugins", self.plugins, "layers")
        self.abas.adicionar("auditoria", "Auditoria", self.auditoria, "history")
        self.corpo.addWidget(self.abas, 1)

    def recarregar(self) -> None:
        try:
            self.plugins.recarregar()
            self.auditoria.recarregar()
        except Exception as erro:  # noqa: BLE001
            self.mostrar_erro(erro, "plugins")
