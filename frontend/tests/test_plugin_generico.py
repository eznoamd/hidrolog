"""Equipamento de um tipo cujo plugin não tem interface (ou não está carregado):
só as abas comuns, com o aviso. Usa o plugin falso dos testes do backend."""

import importlib.util
import sys

import pytest

from app import servico
from app.nucleo import plugins

from .conftest import RAIZ, SENHA, entrar

_MODULO = "plugin_falso_do_backend"


def _plugin_falso():
    if _MODULO not in sys.modules:
        pasta = RAIZ / "backend" / "tests" / "plugin_falso"
        spec = importlib.util.spec_from_file_location(_MODULO, pasta / "__init__.py",
                                                      submodule_search_locations=[str(pasta)])
        mod = importlib.util.module_from_spec(spec)
        sys.modules[_MODULO] = mod
        spec.loader.exec_module(mod)
    return sys.modules[_MODULO].PLUGIN


@pytest.fixture
def banco_com_falso(dados_dir, qapp):
    plugins.registrar(_plugin_falso())
    b = servico.iniciar()
    yield b
    servico.encerrar()
    plugins.remover("falso")


def test_tipo_sem_interface_so_tem_abas_comuns(banco_com_falso, qtbot, tmp_path):
    from app.nucleo.administracao import criar_master
    from hidrolog.aplicacao import JanelaHidrolog

    criar_master(banco_com_falso, "admin", "Admin", SENHA)
    master = servico.autenticar("admin", SENHA)
    eq = servico.criar_equipamento(master, "falso", "Falso 1")
    pasta = tmp_path / "falso"
    pasta.mkdir()
    for i in range(3):
        (pasta / f"falso_2026100100{i:02d}00.csv").write_text(f"valor;{i}")
    servico.importar_caminho(master, eq.id, pasta)

    janela = JanelaHidrolog(confirmar_saida=False)
    qtbot.addWidget(janela)
    janela.show()
    shell = entrar(janela, qtbot, "admin")
    pagina = janela.ctx.abrir_equipamento(eq.id)
    assert pagina.abas.titulos() == ["Qualidade", "Envios", "Importar", "Exportar", "Cadastro"]
    assert "Interface deste sensor indisponível" in pagina.sem_plugin.texto.text()
    envios = pagina.abas.ir_para("envios")
    assert len(envios.tabela.linhas()) == 1 and envios.tabela.linhas()[0]["novas"] == 3
    # a barra lateral não cresce com os sensores
    assert set(shell._secoes) == {"geral", "admin", "recentes"}


def test_plugin_ausente_exporta_generico(banco_com_falso, tmp_path):
    """Sem o plugin carregado, os dados continuam acessíveis pela exportação genérica."""
    from app.nucleo.administracao import criar_master

    criar_master(banco_com_falso, "admin", "Admin", SENHA)
    master = servico.autenticar("admin", SENHA)
    eq = servico.criar_equipamento(master, "falso", "Falso 1")
    pasta = tmp_path / "falso"
    pasta.mkdir()
    (pasta / "falso_20261001000000.csv").write_text("valor;1.5")
    servico.importar_caminho(master, eq.id, pasta)
    plugins.remover("falso")
    assert [f.codigo for f in servico.listar_formatos_exportacao(eq.id)] == ["generico"]
    r = servico.exportar(master, eq.id, None, None, "generico", tmp_path / "saida.csv")
    texto = (tmp_path / "saida.csv").read_text()
    assert r.leituras == 1 and texto.splitlines()[0].startswith("tabela,id,envio_id,tempo,valor")
    assert "falso_leitura" in texto and "1.5" in texto
    plugins.registrar(_plugin_falso())


def test_plugin_removido_nao_deixa_importar(banco_com_falso, qtbot, tmp_path):
    """Sem o plugin, ninguém sabe ler os arquivos: some a aba Importar, o
    equipamento sai da página de importação e o backend recusa o envio. Os
    dados importados antes continuam consultáveis (Envios) e exportáveis."""
    from app.nucleo.administracao import criar_master
    from app.nucleo.erros import ErroServico
    from hidrolog.aplicacao import JanelaHidrolog

    criar_master(banco_com_falso, "admin", "Admin", SENHA)
    master = servico.autenticar("admin", SENHA)
    eq = servico.criar_equipamento(master, "falso", "Falso 1")
    pasta = tmp_path / "falso"
    pasta.mkdir()
    (pasta / "falso_20261001000000.csv").write_text("valor;1.5")
    servico.importar_caminho(master, eq.id, pasta)
    plugins.remover("falso")
    try:
        with pytest.raises(ErroServico, match="sem plugin"):
            servico.importar_caminho(master, eq.id, pasta)
        janela = JanelaHidrolog(confirmar_saida=False)
        qtbot.addWidget(janela)
        janela.show()
        shell = entrar(janela, qtbot, "admin")
        pagina = janela.ctx.abrir_equipamento(eq.id)
        assert pagina.abas.titulos() == ["Qualidade", "Envios", "Exportar", "Cadastro"]
        assert "não é possível importar" in pagina.sem_plugin.texto.text()
        assert len(pagina.abas.ir_para("envios").tabela.linhas()) == 1
        importacao = shell.ir_para("importacao")
        assert importacao.equipamento.findData(eq.id) < 0
    finally:
        plugins.registrar(_plugin_falso())
