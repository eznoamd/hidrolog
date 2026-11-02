"""Janela do app (sem master -> login -> shell) e a função main()."""

from __future__ import annotations

import argparse
import logging
import sys

from PySide6.QtCore import QEventLoop, Qt
from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox, QStackedWidget

from app import servico
from app.nucleo.erros import ErroAutenticacao
from design.componentes import DialogoConfirmacao, TelaAbertura, TelaLogin
from design.tema import aplicar_tema, carregar_marca_da_instalacao, marca_atual

from . import VERSAO
from .nucleo import configuracao, erros, tarefas
from .nucleo.contexto import Contexto
from .nucleo.shell import montar_shell
from .nucleo.telas.sem_master import TelaSemMaster

log = logging.getLogger("hidrolog")
TAMANHO_JANELA = (1440, 900)
MSG_LOGIN = "Usuário ou senha incorretos, ou usuário desativado. Confira e tente de novo."


class JanelaHidrolog(QMainWindow):
    """Pilha com as três telas: sem master, login e o shell da sessão."""

    def __init__(self, confirmar_saida: bool = True):
        super().__init__()
        self.setWindowTitle(marca_atual().titulo_janela)
        self.setMinimumSize(1100, 680)
        self.confirmar_saida = confirmar_saida
        self.pilha = QStackedWidget()
        self.setCentralWidget(self.pilha)
        self.sem_master = TelaSemMaster()
        self.sem_master.verificar.connect(lambda: self.verificar_master(avisar=True))
        self.login = TelaLogin(versao=VERSAO)
        self.login.entrar.connect(self.entrar)
        self.pilha.addWidget(self.sem_master)
        self.pilha.addWidget(self.login)
        self.ctx: Contexto | None = None
        self.shell = None
        self.verificar_master()

    # ------------------------------------------------------------------ fluxo
    def verificar_master(self, avisar: bool = False) -> bool:
        try:
            existe = servico.existe_master()
        except Exception as erro:  # noqa: BLE001
            erros.registrar(erro, "existe_master")
            existe = False
        if existe:
            self.pilha.setCurrentWidget(self.login)
            self.login.usuario.setFocus()
        else:
            self.pilha.setCurrentWidget(self.sem_master)
            if avisar:
                self.sem_master.ainda_sem_master()
        return existe

    def entrar(self, login: str, senha: str) -> None:
        """Confere as credenciais em segundo plano (o hash da senha leva uma
        fração de segundo de propósito): a tela mostra "Verificando credenciais…"."""
        self.login.ocupado(True)
        tarefas.executar(servico.autenticar, login, senha, nome="login",
                         ao_concluir=self._entrou,
                         ao_falhar=lambda erro, l=login: self._login_falhou(l, erro))

    def _entrou(self, usuario) -> None:
        self.login.ocupado(False)
        log.info("login: %s (%s)", usuario.login, usuario.perfil)
        self.abrir_sessao(usuario)

    def _login_falhou(self, login: str, erro) -> None:
        self.login.ocupado(False)
        if isinstance(erro, ErroAutenticacao):
            log.info("login recusado: %s", login)
            self.login.mostrar_erro(MSG_LOGIN)
            return
        erros.registrar(erro, "login")
        self.login.mostrar_erro(erros.mensagem(erro))

    def abrir_sessao(self, usuario) -> None:
        self._fechar_shell()
        self.ctx = Contexto(usuario)
        self.ctx.sessao_expirada.connect(self._sessao_expirada, Qt.ConnectionType.QueuedConnection)
        self.shell = montar_shell(self.ctx)
        self.shell.sair_solicitado.connect(self.sair)
        self.pilha.addWidget(self.shell)
        self.pilha.setCurrentWidget(self.shell)

    def sair(self) -> None:
        if self.confirmar_saida and not DialogoConfirmacao.perguntar(
                self, "Sair do sistema?", "Você vai voltar para a tela de login.", "Sair"):
            return
        self.encerrar_sessao()

    def encerrar_sessao(self, mensagem: str = "") -> None:
        self._fechar_shell()
        self.login.limpar()
        self.pilha.setCurrentWidget(self.login)
        if mensagem:
            self.login.mostrar_erro(mensagem)

    def _sessao_expirada(self, mensagem: str) -> None:
        if self.shell is not None:
            self.encerrar_sessao(mensagem)

    def _fechar_shell(self) -> None:
        if self.shell is not None:
            self.pilha.removeWidget(self.shell)
            self.shell.deleteLater()
            self.shell = None
        if self.ctx is not None:
            self.ctx.deleteLater()
            self.ctx = None


def _gancho_excecoes(tipo, valor, tb) -> None:
    """Exceção não tratada na interface: vai para o log, e a tela mostra uma
    mensagem curta (sem traceback)."""
    log.error("exceção não tratada", exc_info=(tipo, valor, tb))
    if QApplication.instance() is not None and tipo is not KeyboardInterrupt:
        QMessageBox.warning(None, marca_atual().nome_app,
                            f"{erros.mensagem(valor)}\n\nLog: {configuracao.caminho_log()}")


def _iniciar_com_abertura(app: QApplication) -> None:
    """Abre o banco (migrações, plugins, regras) em segundo plano, com a tela
    de abertura animada; levanta o erro de servico.iniciar(), se houver."""
    abertura = TelaAbertura("Abrindo o banco de dados…")
    abertura.show()
    laco = QEventLoop()
    resultado: dict = {}

    def _fim(**r):
        resultado.update(r)
        laco.quit()

    tarefas.executar(servico.iniciar, nome="abrir o banco",
                     ao_concluir=lambda _b: _fim(ok=True), ao_falhar=lambda e: _fim(erro=e))
    laco.exec()
    abertura.close()
    if "erro" in resultado:
        raise resultado["erro"]


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    ap = argparse.ArgumentParser(prog="python -m hidrolog", description="Hidrolog: dados de sensores ambientais")
    ap.add_argument("--tema", choices=("claro", "escuro"), help="tema da interface (padrão: o último usado)")
    args, resto_qt = ap.parse_known_args(argv[1:])

    destino_log = configuracao.configurar_log()
    carregar_marca_da_instalacao(configuracao.diretorio_marca())
    app = QApplication([argv[0], *resto_qt])
    app.setApplicationName(marca_atual().nome_app)
    tarefas.instalar_coleta_de_lixo(app)
    app.setOrganizationName(marca_atual().laboratorio or marca_atual().nome_app)
    app.setApplicationVersion(VERSAO)
    aplicar_tema(app, args.tema or configuracao.tema_salvo())
    sys.excepthook = _gancho_excecoes
    log.info("Hidrolog %s iniciando (log em %s)", VERSAO, destino_log)

    try:
        _iniciar_com_abertura(app)
    except Exception as erro:  # noqa: BLE001
        erros.registrar(erro, "abrir o banco")
        QMessageBox.critical(None, marca_atual().nome_app,
                             "Não foi possível abrir o banco de dados do Hidrolog.\n\n"
                             f"{erros.mensagem(erro)}\n\nDetalhes no log: {destino_log}")
        return 1

    janela = JanelaHidrolog()
    janela.resize(*TAMANHO_JANELA)
    janela.show()
    try:
        return app.exec()
    finally:
        tarefas.esperar_todas(30000)
        servico.encerrar()
        log.info("Hidrolog encerrado")


if __name__ == "__main__":
    sys.exit(main())
