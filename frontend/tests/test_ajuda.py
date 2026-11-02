"""Central de ajuda: tópicos, links, perfis e busca."""

import re

from PySide6.QtCore import Qt, QUrl

from hidrolog import ajuda

from .conftest import entrar

LINK = re.compile(r"\]\(ajuda:([a-z0-9-]+)\)")


def test_todo_topico_tem_texto_e_os_links_apontam_para_topicos():
    assert len(ajuda.TOPICO) == len(ajuda.TOPICOS)            # chaves únicas
    for t in ajuda.TOPICOS:
        md = ajuda.texto(t)
        assert md.startswith("# "), t.chave
        for alvo in LINK.findall(md):
            assert alvo in ajuda.TOPICO, f"{t.chave}: link para tópico inexistente {alvo!r}"


def test_ajuda_e_generica():
    """A ajuda é do app: não cita repositório nem pacote de nenhum plugin."""
    pacote = re.compile(r"hidrolog-plugin-|hidrolog_(?!nucleo\b)\w+")
    for t in ajuda.TOPICOS:
        assert not pacote.search(ajuda.texto(t)), t.chave


def test_topicos_por_perfil_e_busca():
    grupos = [g for g, _ in ajuda.agrupados("leitura")]
    assert "Administração" not in grupos and "Primeiros passos" in grupos
    assert "Administração" in [g for g, _ in ajuda.agrupados("master")]
    assert {t.chave for t in ajuda.buscar("copia seguranca", "master")} >= {"instalacao"}
    assert "instalacao" not in {t.chave for t in ajuda.buscar("cópia segurança", "leitura")}
    assert [t.chave for t in ajuda.buscar("", "leitura")] == [t.chave for t in ajuda.topicos("leitura")]


def test_botao_de_ajuda_abre_a_central(usuarios, janela, qtbot):
    shell = entrar(janela, qtbot, "ler")
    qtbot.mouseClick(shell.cabecalho.ajuda, Qt.MouseButton.LeftButton)
    pagina = shell.pagina("ajuda")
    assert shell.area.currentWidget() is pagina and pagina.atual == "boas-vindas"
    assert not shell._paginas["ajuda"].botao.isVisible()
    assert "plugins" not in pagina.topicos_listados()
    assert "O que é o Hidrolog" in pagina.leitor.toPlainText()
    # link entre tópicos
    pagina.leitor.anchorClicked.emit(QUrl("ajuda:importar"))
    assert pagina.atual == "importar" and "Importar dados" in pagina.leitor.toPlainText()
    # tópico de administração: o perfil Leitura não abre
    pagina.leitor.anchorClicked.emit(QUrl("ajuda:plugins"))
    assert pagina.atual == "importar" and pagina.aviso.isVisible()
    # busca
    pagina.busca.setText("senha")
    assert "conta" in pagina.topicos_listados() and "inicio" not in pagina.topicos_listados()
    pagina.busca.setText("xyzzy")
    assert pagina.topicos_listados() == [] and pagina.nada.isVisibleTo(pagina)


def test_master_ve_a_administracao(master, janela, qtbot):
    shell = entrar(janela, qtbot, "admin")
    pagina = shell.ir_para("ajuda")
    assert {"usuarios", "plugins", "instalacao", "criar-plugin"} <= set(pagina.topicos_listados())
    assert pagina.abrir("plugins") and "um plugin é um programa" in pagina.leitor.toPlainText()
