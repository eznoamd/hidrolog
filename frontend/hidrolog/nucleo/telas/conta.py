"""Minha conta: o próprio perfil, nome, senha, tema e os últimos envios.
Qualquer perfil abre (pelo menu do usuário no cabeçalho, não pela barra lateral)."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication, QHBoxLayout, QVBoxLayout

from app import servico
from app.nucleo.erros import ErroServico
from design.componentes import Avatar, Botao, Cartao, TabelaFiltravel, formatos, rotulo, selo_perfil
from design.tema import ESPACO, aplicar_tema, gerenciador, modo_atual

from .. import configuracao
from .comum import DialogoFormulario, PaginaBase
from .historico import colunas_historico, linha_envio
from .inicio import altura_tabela
from .usuarios import SENHA_MINIMA, _campo_texto

ULTIMOS_ENVIOS = 5

O_QUE_O_PERFIL_FAZ = {
    "master": "Administra usuários, plugins e configurações, além de tudo o que o perfil Cadastro faz.",
    "cadastro": "Cadastra equipamentos, importa dados e ajusta as regras de qualidade; também consulta e exporta.",
    "leitura": "Consulta e exporta os dados; não altera nada no banco.",
}


class PaginaConta(PaginaBase):
    depende_de = ("envios",)

    def __init__(self, ctx):
        super().__init__(ctx, "Minha conta", "Seus dados de acesso e preferências neste computador.")

        perfil = Cartao("Perfil")
        linha = QHBoxLayout()
        linha.setSpacing(ESPACO["lg"])
        self.avatar = Avatar(ctx.usuario.nome, 56)
        linha.addWidget(self.avatar)
        textos = QVBoxLayout()
        textos.setSpacing(ESPACO["xs"])
        self.nome = rotulo("", "titulo")
        textos.addWidget(self.nome)
        detalhe = QHBoxLayout()
        detalhe.setSpacing(ESPACO["sm"])
        self.login = rotulo("", "secundario", mono=True)
        detalhe.addWidget(self.login)
        detalhe.addWidget(selo_perfil(ctx.usuario.perfil))
        detalhe.addStretch(1)
        textos.addLayout(detalhe)
        self.desde = rotulo("", "legenda")
        textos.addWidget(self.desde)
        linha.addLayout(textos, 1)
        self.editar_nome = Botao("Editar nome", "secundaria", "pencil")
        self.editar_nome.clicked.connect(self.abrir_editar_nome)
        linha.addWidget(self.editar_nome)
        perfil.corpo.addLayout(linha)
        perfil.corpo.addWidget(rotulo(O_QUE_O_PERFIL_FAZ.get(ctx.usuario.perfil, ""), "secundario", quebra=True))
        perfil.corpo.addWidget(rotulo("O login e o perfil só são mudados pelo master.", "legenda", quebra=True))
        self.corpo.addWidget(perfil)

        seguranca = Cartao("Senha")
        seguranca.corpo.addWidget(rotulo(
            f"Use uma senha só sua, com pelo menos {SENHA_MINIMA} caracteres. Para trocar, confirme a senha atual. "
            "Se esquecê-la, peça ao master uma senha nova.", "secundario", quebra=True))
        linha_senha = QHBoxLayout()
        self.trocar_senha = Botao("Trocar minha senha", "secundaria", "key-round")
        self.trocar_senha.clicked.connect(self.abrir_trocar_senha)
        linha_senha.addWidget(self.trocar_senha)
        linha_senha.addStretch(1)
        seguranca.corpo.addLayout(linha_senha)
        self.corpo.addWidget(seguranca)

        aparencia = Cartao("Aparência")
        aparencia.corpo.addWidget(rotulo("O tema fica guardado neste computador.", "secundario"))
        linha_tema = QHBoxLayout()
        linha_tema.setSpacing(ESPACO["sm"])
        self.temas: dict[str, Botao] = {}
        for modo, texto, ic in (("claro", "Claro", "sun"), ("escuro", "Escuro", "moon")):
            botao = Botao(texto, "secundaria", ic)
            botao.clicked.connect(lambda _=False, m=modo: self.definir_tema(m))
            self.temas[modo] = botao
            linha_tema.addWidget(botao)
        linha_tema.addStretch(1)
        gerenciador().tema_alterado.connect(self._marcar_tema)
        aparencia.corpo.addLayout(linha_tema)
        self.corpo.addWidget(aparencia)

        self.cartao_envios = Cartao("Seus últimos envios")
        self.envios = TabelaFiltravel(colunas_historico(compacta=True), mostrar_busca=False, ordenar_por="quando",
                                      decrescente=True, embutida=True, titulo_vazio="Você ainda não enviou dados",
                                      icone_vazio="history")
        self.envios.contagem.hide()
        self.cartao_envios.corpo.addWidget(self.envios)
        self.cartao_envios.setVisible(ctx.pode("cadastro"))   # o perfil Leitura não importa
        self.corpo.addWidget(self.cartao_envios)
        self.corpo.addStretch(1)
        self._mostrar_usuario()

    def _mostrar_usuario(self) -> None:
        u = self.ctx.usuario
        self.nome.setText(u.nome)
        self.login.setText(u.login)
        self.avatar.definir_nome(u.nome)
        self.desde.setText(f"Usuário desde {formatos.data(u.criado_em)}")

    def ao_mostrar(self) -> None:
        self._marcar_tema()
        super().ao_mostrar()

    def _marcar_tema(self, *_) -> None:
        """O tema em uso fica destacado (botão primário)."""
        for modo, botao in self.temas.items():
            botao.definir_variante("primaria" if modo == modo_atual() else "secundaria")

    def recarregar(self) -> None:
        if not self.ctx.pode("cadastro"):
            return
        try:
            envios = servico.meus_envios(self.ctx.usuario, ULTIMOS_ENVIOS)
        except Exception as erro:  # noqa: BLE001
            self.mostrar_erro(erro, "carregar seus envios")
            return
        self.envios.definir_linhas([linha_envio(e) for e in envios])
        self.envios.setFixedHeight(altura_tabela(len(envios)))

    # ------------------------------------------------------------------ ações
    def definir_tema(self, modo: str) -> None:
        if modo != modo_atual():
            aplicar_tema(QApplication.instance(), modo)
            configuracao.salvar_tema(modo)

    def abrir_editar_nome(self) -> "DialogoMeuNome":
        d = DialogoMeuNome(self.ctx, self.window())
        d.accepted.connect(self._nome_alterado)
        d.open()
        return d

    def _nome_alterado(self) -> None:
        u = self.ctx.usuario
        if self.ctx.shell is not None:
            self.ctx.shell.definir_usuario(u.nome, u.perfil, u.login)
        self._mostrar_usuario()
        self.mostrar_aviso("Nome atualizado.")

    def abrir_trocar_senha(self) -> "DialogoMinhaSenha":
        d = DialogoMinhaSenha(self.ctx, self.window())
        d.accepted.connect(lambda: self.mostrar_aviso("Senha trocada. Ela vale a partir do próximo login."))
        d.open()
        return d


class DialogoMeuNome(DialogoFormulario):
    def __init__(self, ctx, parent=None):
        super().__init__("Editar nome", "O nome aparece no cabeçalho e no histórico. O login não muda.",
                         "Salvar", parent)
        self.ctx = ctx
        self.nome = self.campo("Nome", _campo_texto("Nome e sobrenome"))
        self.nome.setText(ctx.usuario.nome)

    def validar(self) -> bool:
        if not self.nome.text().strip():
            self.erro_campo(self.nome, "Informe o nome.")
            return False
        return True

    def salvar(self):
        self.ctx.usuario = servico.alterar_meu_nome(self.ctx.usuario, self.nome.text())
        return self.ctx.usuario


class DialogoMinhaSenha(DialogoFormulario):
    def __init__(self, ctx, parent=None):
        super().__init__("Trocar minha senha", "Confirme a senha atual e escolha a nova.", "Trocar senha", parent)
        self.ctx = ctx
        self.atual = self.campo("Senha atual", _campo_texto("", True))
        self.senha = self.campo("Nova senha", _campo_texto(f"mínimo de {SENHA_MINIMA} caracteres", True))
        self.confirma = self.campo("Confirmar nova senha", _campo_texto("", True))

    def validar(self) -> bool:
        if not self.atual.text():
            self.erro_campo(self.atual, "Informe a senha atual.")
            return False
        if len(self.senha.text()) < SENHA_MINIMA:
            self.erro_campo(self.senha, f"A senha precisa de pelo menos {SENHA_MINIMA} caracteres.")
            return False
        if self.senha.text() != self.confirma.text():
            self.erro_campo(self.confirma, "As senhas não coincidem.")
            return False
        return True

    def salvar(self):
        servico.trocar_minha_senha(self.ctx.usuario, self.atual.text(), self.senha.text())
        return True

    def tratar_erro_salvar(self, erro: BaseException) -> bool:
        if isinstance(erro, ErroServico) and "senha atual" in str(erro):
            self.erro_campo(self.atual, "A senha atual não confere.")
            return True
        if isinstance(erro, ErroServico) and "igual a atual" in str(erro):
            self.erro_campo(self.senha, "A nova senha é igual à atual.")
            return True
        return False
