"""Menu do usuário no cabeçalho e a página Minha conta."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from app import servico
from design.componentes import iniciais
from design.tema import aplicar_tema, modo_atual

from .conftest import SENHA, entrar


def _abrir_conta(shell, qtbot):
    menu = shell.cabecalho.usuario
    qtbot.mouseClick(menu, Qt.MouseButton.LeftButton)
    assert menu.painel.isVisible()
    qtbot.mouseClick(menu.painel.item_conta, Qt.MouseButton.LeftButton)
    assert not menu.painel.isVisible()
    return shell.pagina("conta")


def test_iniciais():
    assert iniciais("Carla de Souza Cadastro") == "CC"
    assert iniciais("Ana") == "AN"
    assert iniciais("  ") == "?"


def test_menu_do_usuario_mostra_nome_perfil_e_abre_a_conta(usuarios, janela, qtbot):
    shell = entrar(janela, qtbot, "cad")
    menu = shell.cabecalho.usuario
    assert (menu.nome.text(), menu.subtitulo.text(), menu.avatar.texto) == ("Carla Cadastro", "Cadastro", "CC")
    assert "cad" in menu.toolTip()                                   # o login fica na dica
    pagina = _abrir_conta(shell, qtbot)
    assert shell.area.currentWidget() is pagina
    assert shell.cabecalho.pagina.text() == "Minha conta"
    assert not shell._paginas["conta"].botao.isVisible()       # fora da barra lateral
    assert pagina.login.text() == "cad" and pagina.cartao_envios.isVisibleTo(pagina)


def test_editar_o_proprio_nome(usuarios, janela, qtbot):
    shell = entrar(janela, qtbot, "ler")
    pagina = _abrir_conta(shell, qtbot)
    assert not pagina.cartao_envios.isVisibleTo(pagina)        # Leitura não importa
    d = pagina.abrir_editar_nome()
    d.nome.setText("Lúcio L. Leitura")
    d._confirmar()
    assert shell.cabecalho.usuario.nome.text() == "Lúcio L. Leitura"
    assert pagina.nome.text() == "Lúcio L. Leitura"
    assert servico.autenticar("ler", SENHA).nome == "Lúcio L. Leitura"


def test_trocar_a_propria_senha(usuarios, janela, qtbot):
    shell = entrar(janela, qtbot, "cad")
    pagina = _abrir_conta(shell, qtbot)
    d = pagina.abrir_trocar_senha()
    d.atual.setText("senha-errada")
    d.senha.setText("nova-senha-123")
    d.confirma.setText("nova-senha-123")
    d._confirmar()
    assert d.isVisible() and "não confere" in d._erros[d.atual].text()
    d.atual.setText(SENHA)
    d._confirmar()
    assert not d.isVisible()
    assert servico.autenticar("cad", "nova-senha-123").login == "cad"


def test_tema_pela_conta(usuarios, janela, qtbot):
    shell = entrar(janela, qtbot, "cad")
    pagina = _abrir_conta(shell, qtbot)
    assert pagina.temas["claro"].property("variante") == "primaria"
    escuro = pagina.temas["escuro"]
    try:
        qtbot.mouseClick(escuro, Qt.MouseButton.LeftButton)
        assert modo_atual() == "escuro"
        assert shell.lateral.botao_tema.text() == "Tema claro"
        assert escuro.property("variante") == "primaria"
        assert pagina.temas["claro"].property("variante") == "secundaria"
    finally:
        aplicar_tema(QApplication.instance(), "claro")
