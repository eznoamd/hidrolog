"""Login, tela de "master não existe", sessão e tema."""

from PySide6.QtCore import Qt

from app import servico
from app.nucleo.administracao import criar_master
from hidrolog.nucleo import configuracao
from hidrolog.nucleo.telas.sem_master import comando_criar_master

from .conftest import SENHA, entrar


def test_sem_master_mostra_o_comando(janela, qtbot, banco, dados_dir):
    assert janela.pilha.currentWidget() is janela.sem_master
    comando = janela.sem_master.comando_texto
    assert "-m app criar-master --login admin" in comando
    assert str(dados_dir) in comando           # aponta para o mesmo banco
    assert comando == comando_criar_master()
    # clicar em continuar sem master: avisa e continua na mesma tela
    qtbot.mouseClick(janela.sem_master.continuar, Qt.MouseButton.LeftButton)
    assert janela.pilha.currentWidget() is janela.sem_master
    assert "Ainda não há nenhum master" in janela.sem_master.aviso.texto.text()
    # o app nunca cria o master: depois do comando de linha, segue para o login
    criar_master(banco, "admin", "Admin", SENHA)
    qtbot.mouseClick(janela.sem_master.continuar, Qt.MouseButton.LeftButton)
    assert janela.pilha.currentWidget() is janela.login


def test_login_errado_mostra_erro(master, janela, qtbot):
    assert janela.pilha.currentWidget() is janela.login
    assert entrar(janela, qtbot, "admin", "senha-errada") is None
    assert janela.login.aviso.isVisible()
    assert "incorretos" in janela.login.aviso.texto.text()
    assert janela.login.usuario.property("invalido") == "true"
    assert janela.pilha.currentWidget() is janela.login


def test_login_certo_abre_o_shell(master, janela, qtbot):
    shell = entrar(janela, qtbot, "admin")
    assert shell is not None and janela.pilha.currentWidget() is shell
    assert shell.cabecalho.usuario.nome.text() == "Administradora Teste"
    assert shell.perfil == "master"
    assert janela.windowTitle() == "Hidrolog"          # sem pasta de marca: genérico
    assert shell.cabecalho.pagina.text() == "Início"


def test_sair_volta_ao_login(master, janela, qtbot):
    shell = entrar(janela, qtbot, "admin")
    qtbot.mouseClick(shell.cabecalho.usuario, Qt.MouseButton.LeftButton)
    assert shell.cabecalho.usuario.painel.isVisible()
    qtbot.mouseClick(shell.cabecalho.usuario.painel.item_sair, Qt.MouseButton.LeftButton)
    assert janela.shell is None
    assert janela.pilha.currentWidget() is janela.login
    assert janela.login.usuario.text() == ""


def test_usuario_desativado_durante_a_sessao_volta_ao_login(usuarios, master, janela, qtbot):
    entrar(janela, qtbot, "cad")
    cad = next(u for u in servico.listar_usuarios(master) if u.login == "cad")
    servico.alterar_usuario(master, cad.id, ativo=False)
    janela.shell.ir_para("historico")
    qtbot.waitUntil(lambda: janela.shell is None, timeout=3000)
    assert janela.pilha.currentWidget() is janela.login
    assert "sessão" in janela.login.aviso.texto.text()


def test_tema_fica_salvo(master, janela, qtbot):
    from design.tema import modo_atual
    shell = entrar(janela, qtbot, "admin")
    assert modo_atual() == "claro"
    qtbot.mouseClick(shell.lateral.botao_tema, Qt.MouseButton.LeftButton)
    try:
        assert modo_atual() == "escuro"
        assert configuracao.tema_salvo() == "escuro"
    finally:
        qtbot.mouseClick(shell.lateral.botao_tema, Qt.MouseButton.LeftButton)
    assert configuracao.tema_salvo() == "claro"


def test_login_mostra_carregamento_enquanto_confere(usuarios, janela, qtbot, monkeypatch):
    import time

    from app import servico as servico_mod

    original = servico_mod.autenticar

    def lento(login, senha):
        time.sleep(0.3)
        return original(login, senha)

    monkeypatch.setattr(servico_mod, "autenticar", lento)
    janela.login.usuario.setText("ler")
    janela.login.senha.setText(SENHA)
    qtbot.mouseClick(janela.login.botao, Qt.MouseButton.LeftButton)
    assert janela.login.esta_ocupado
    assert not janela.login.usuario.isEnabled() and not janela.login.botao.isEnabled()
    assert janela.login.botao.text().strip() == "Entrando…"
    qtbot.waitUntil(lambda: not janela.login.esta_ocupado, timeout=10000)
    assert janela.shell is not None and janela.login.botao.text().strip() == "Entrar"


def test_abertura_do_banco_em_segundo_plano(dados_dir, qapp):
    from PySide6.QtCore import QCoreApplication, QEvent

    from app import servico as servico_mod
    from hidrolog.aplicacao import _iniciar_com_abertura

    # no app a abertura roda antes de existir qualquer janela; aqui, termina de
    # destruir as janelas dos testes anteriores antes de abrir o laço de eventos
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    qapp.processEvents()
    _iniciar_com_abertura(qapp)
    try:
        assert not servico_mod.existe_master()          # banco novo, aberto pela tarefa
    finally:
        servico_mod.encerrar()
