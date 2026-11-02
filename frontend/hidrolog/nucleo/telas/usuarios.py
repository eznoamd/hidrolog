"""Usuários (só master): listar, criar, editar nome/perfil, ativar/desativar
e trocar senha. O perfil master não é dado nem retirado aqui e um master não
é desativado (regras do backend, refletidas na tela)."""

from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLineEdit

from app import servico
from app.nucleo.erros import Conflito
from app.nucleo.tipos import Usuario
from design.componentes import (
    Botao, Cartao, Coluna, DialogoConfirmacao, TabelaFiltravel, rotulo, selo_perfil,
)
from design.tema import ESPACO, PERFIS

from .comum import DialogoFormulario, PaginaBase

SENHA_MINIMA = 8
PERFIS_DO_APP = [("leitura", "Leitura — só consulta e exporta"),
                 ("cadastro", "Cadastro — importa dados, cadastra equipamentos e consulta")]


class PaginaUsuarios(PaginaBase):
    depende_de = ("usuarios",)

    def __init__(self, ctx):
        super().__init__(ctx, "Usuários",
                         "Somente o perfil master vê esta página. Cada pessoa tem o próprio usuário; não compartilhe senhas.")
        self.novo = Botao("Novo usuário", "primaria", "plus")
        self.novo.clicked.connect(self.novo_usuario)
        self.adicionar_acao(self.novo)

        legenda = Cartao(margem=ESPACO["md"])
        lin = QHBoxLayout()
        lin.setSpacing(ESPACO["xl"])
        for perfil, desc in (("master", "administra usuários; criado só pelo comando de linha"),
                             ("cadastro", "importa dados, cadastra equipamentos e consulta"),
                             ("leitura", "só consulta e exporta")):
            item = QHBoxLayout()
            item.setSpacing(ESPACO["sm"])
            item.addWidget(selo_perfil(perfil))
            item.addWidget(rotulo(desc, "secundario"))
            lin.addLayout(item)
        lin.addStretch(1)
        legenda.corpo.addLayout(lin)
        self.corpo.addWidget(legenda)

        self.tabela = TabelaFiltravel([
            Coluna("nome", "Nome", largura=220),
            Coluna("login", "Usuário", "mono", largura=150),
            Coluna("perfil", "Perfil", "selo", selo=lambda v: PERFIS[v], largura=120),
            Coluna("ativo", "Situação", "selo", selo=lambda v: ("Ativo", "sucesso") if v else ("Desativado", "neutro"),
                   largura=120),
            Coluna("criado", "Criado em", "data"),
            Coluna("vazio", "", estica=True, formatar=lambda _: ""),
        ], texto_busca="Buscar por nome ou usuário…", titulo_vazio="Nenhum usuário")
        self.tabela.adicionar_filtro("perfil", "Todos os perfis")
        self.editar = Botao("Editar", "secundaria", "pencil")
        self.senha = Botao("Trocar senha", "secundaria", "key-round")
        self.ativar = Botao("Desativar", "secundaria", "lock")
        for b in (self.editar, self.senha, self.ativar):
            b.setEnabled(False)
            self.tabela.adicionar_acao(b)
        self.tabela.selecao_alterada.connect(self._selecao)
        self.tabela.linha_ativada.connect(lambda linha: self.editar_usuario(linha["_usuario"]))
        self.editar.clicked.connect(lambda: self.editar_usuario(self._selecionado()))
        self.senha.clicked.connect(lambda: self.trocar_senha(self._selecionado()))
        self.ativar.clicked.connect(lambda: self.alternar_ativo(self._selecionado()))
        self.tabela.setMinimumHeight(360)
        self.corpo.addWidget(self.tabela, 1)

    # ------------------------------------------------------------------ dados
    def recarregar(self) -> None:
        try:
            usuarios = servico.listar_usuarios(self.ctx.usuario)
        except Exception as erro:  # noqa: BLE001
            self.mostrar_erro(erro, "listar usuários")
            return
        self.tabela.definir_linhas([
            {"nome": u.nome, "login": u.login, "perfil": u.perfil, "ativo": u.ativo, "criado": u.criado_em,
             "vazio": "", "_usuario": u} for u in usuarios])
        self._selecao(self.tabela.selecao())

    def _selecionado(self) -> Usuario | None:
        sel = self.tabela.selecao()
        return sel[0]["_usuario"] if len(sel) == 1 else None

    def _selecao(self, linhas) -> None:
        u = linhas[0]["_usuario"] if len(linhas) == 1 else None
        self.editar.setEnabled(u is not None)
        self.senha.setEnabled(u is not None)
        # um master não é desativado pelo app (regra do backend)
        self.ativar.setEnabled(u is not None and u.perfil != "master")
        reativar = u is not None and not u.ativo
        self.ativar.setText(f" {'Reativar' if reativar else 'Desativar'}")
        self.ativar.definir_icone("circle-check" if reativar else "lock")
        self.ativar.setToolTip("Um usuário master não pode ser desativado pelo app."
                               if u is not None and u.perfil == "master" else "")

    def selecionar_login(self, login: str) -> None:
        modelo = self.tabela.tabela.model()
        for linha in range(modelo.rowCount()):
            if modelo.index(linha, 1).data() == login:
                self.tabela.tabela.selectRow(linha)
                return

    # ------------------------------------------------------------------ ações
    def novo_usuario(self) -> "DialogoUsuario":
        d = DialogoUsuario(self.ctx, None, self.window())
        d.accepted.connect(lambda: self._salvo(f"Usuário {d.resultado.login} criado."))
        d.open()
        return d

    def editar_usuario(self, u: Usuario | None) -> "DialogoUsuario | None":
        if u is None:
            return None
        d = DialogoUsuario(self.ctx, u, self.window())
        d.accepted.connect(lambda: self._salvo(f"Usuário {u.login} atualizado."))
        d.open()
        return d

    def trocar_senha(self, u: Usuario | None) -> "DialogoSenha | None":
        if u is None:
            return None
        d = DialogoSenha(self.ctx, u, self.window())
        d.accepted.connect(lambda: self._salvo(f"Senha de {u.login} trocada."))
        d.open()
        return d

    def alternar_ativo(self, u: Usuario | None, confirmar: bool = True) -> None:
        if u is None or u.perfil == "master":
            return
        if u.ativo and confirmar and not DialogoConfirmacao.perguntar(
                self.window(), f"Desativar {u.nome}?",
                f"{u.login} não conseguirá mais entrar. Os envios feitos por esta pessoa continuam no histórico. "
                "Você pode reativar o usuário depois.", "Desativar usuário", destrutivo=True):
            return
        try:
            servico.alterar_usuario(self.ctx.usuario, u.id, ativo=not u.ativo)
        except Exception as erro:  # noqa: BLE001
            self.mostrar_erro(erro, "ativar/desativar usuário")
            return
        self._salvo(f"Usuário {u.login} {'desativado' if u.ativo else 'reativado'}.")

    def _salvo(self, texto: str) -> None:
        self.ctx.dados_alterados.emit("usuarios")
        self.mostrar_aviso(texto, "sucesso")


def _campo_texto(placeholder: str = "", senha: bool = False) -> QLineEdit:
    c = QLineEdit()
    c.setPlaceholderText(placeholder)
    if senha:
        c.setEchoMode(QLineEdit.EchoMode.Password)
    return c


class DialogoUsuario(DialogoFormulario):
    """Criar (usuario=None) ou editar nome e perfil."""

    def __init__(self, ctx, usuario: Usuario | None = None, parent=None):
        novo = usuario is None
        super().__init__("Novo usuário" if novo else f"Editar {usuario.nome}",
                         "A pessoa entra com o usuário e a senha definidos aqui. O master pode trocar a senha depois."
                         if novo else "O usuário (login) não muda. Para trocar a senha, use “Trocar senha”.",
                         "Criar usuário" if novo else "Salvar", parent)
        self.ctx = ctx
        self.usuario = usuario
        self.nome = self.campo("Nome", _campo_texto("Nome completo"))
        self.login = self.campo("Usuário", _campo_texto("ex.: ana.souza"),
                                "Sem espaços. É o que a pessoa digita para entrar." if novo else "")
        self.perfil = QComboBox()
        if usuario is not None and usuario.perfil == "master":
            self.perfil.addItem("Master — administra usuários", "master")
            self.perfil.setEnabled(False)
            self.campo("Perfil", self.perfil, "O perfil master não é dado nem retirado pelo app.")
        else:
            for codigo, texto in PERFIS_DO_APP:
                self.perfil.addItem(texto, codigo)
            self.campo("Perfil", self.perfil)
        if novo:
            self.senha = self.campo("Senha", _campo_texto(f"mínimo de {SENHA_MINIMA} caracteres", True))
            self.confirma = self.campo("Confirmar senha", _campo_texto("", True))
        else:
            self.nome.setText(usuario.nome)
            self.login.setText(usuario.login)
            self.login.setReadOnly(True)
            self.login.setEnabled(False)
            self.perfil.setCurrentIndex(max(0, self.perfil.findData(usuario.perfil)))

    def validar(self) -> bool:
        ok = True
        if not self.nome.text().strip():
            self.erro_campo(self.nome, "Informe o nome.")
            ok = False
        if self.usuario is None:
            login = self.login.text().strip()
            if not login:
                self.erro_campo(self.login, "Informe o usuário.")
                ok = False
            elif any(c.isspace() for c in login):
                self.erro_campo(self.login, "O usuário não pode ter espaços.")
                ok = False
            if len(self.senha.text()) < SENHA_MINIMA:
                self.erro_campo(self.senha, f"A senha precisa de pelo menos {SENHA_MINIMA} caracteres.")
                ok = False
            elif self.senha.text() != self.confirma.text():
                self.erro_campo(self.confirma, "As senhas não coincidem.")
                ok = False
        return ok

    def salvar(self) -> Usuario:
        u = self.ctx.usuario
        if self.usuario is None:
            return servico.criar_usuario(u, self.login.text().strip(), self.nome.text().strip(),
                                         self.senha.text(), self.perfil.currentData())
        perfil = None if self.usuario.perfil == "master" else self.perfil.currentData()
        return servico.alterar_usuario(u, self.usuario.id, nome=self.nome.text().strip(), perfil=perfil)

    def tratar_erro_salvar(self, erro) -> bool:
        if isinstance(erro, Conflito) and self.usuario is None:
            self.erro_campo(self.login, f"Já existe o usuário “{self.login.text().strip()}”. Escolha outro.")
            return True
        return False


class DialogoSenha(DialogoFormulario):
    def __init__(self, ctx, usuario: Usuario, parent=None):
        super().__init__(f"Trocar a senha de {usuario.nome}",
                         f"A nova senha vale a partir do próximo login de {usuario.login}. "
                         "Combine com a pessoa um jeito seguro de passá-la.", "Trocar senha", parent)
        self.ctx = ctx
        self.usuario = usuario
        self.senha = self.campo("Nova senha", _campo_texto(f"mínimo de {SENHA_MINIMA} caracteres", True))
        self.confirma = self.campo("Confirmar senha", _campo_texto("", True))

    def validar(self) -> bool:
        if len(self.senha.text()) < SENHA_MINIMA:
            self.erro_campo(self.senha, f"A senha precisa de pelo menos {SENHA_MINIMA} caracteres.")
            return False
        if self.senha.text() != self.confirma.text():
            self.erro_campo(self.confirma, "As senhas não coincidem.")
            return False
        return True

    def salvar(self) -> None:
        servico.trocar_senha(self.ctx.usuario, self.usuario.id, self.senha.text())
        return True
