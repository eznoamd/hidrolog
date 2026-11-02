"""Configurações → Plugins (só master): lista, importar com confirmação e senha,
desativar, auditoria."""

import json
from dataclasses import replace

import pytest

from app import servico
from app.nucleo import plugins

from .conftest import PLUGIN_TERMOMETRO, SENHA, entrar, esperar_tarefas


@pytest.fixture
def estacao_interna(monkeypatch):
    """O sensor de teste visto como um plugin instalado por entry point (interno)."""
    monkeypatch.setitem(plugins._situacoes, "estacao", replace(plugins._situacoes["estacao"], origem="interno"))


def test_plugins_so_para_o_master(usuarios, janela, qtbot, estacao_interna):
    shell = entrar(janela, qtbot, "admin")
    pagina = shell.ir_para("configuracoes")
    linhas = {l["codigo"]: l for l in pagina.plugins.tabela.linhas()}
    assert linhas["estacao"]["estado"] == "ativo" and linhas["estacao"]["origem"] == "Interno"
    assert pagina.abas.titulos() == ["Plugins", "Auditoria"]
    janela.encerrar_sessao()
    shell = entrar(janela, qtbot, "cad")
    assert shell.ir_para("configuracoes") is None


def test_importar_plugin_da_pasta_com_senha(usuarios, janela, qtbot, dados_dir, monkeypatch):
    shell = entrar(janela, qtbot, "admin")
    pagina = shell.ir_para("configuracoes")
    aba = pagina.plugins
    monkeypatch.setattr(aba, "escolher_local", lambda: str(PLUGIN_TERMOMETRO))
    aba.importar_de("computador")
    esperar_tarefas(qtbot)
    qtbot.waitUntil(lambda: aba.dialogo is not None and aba.dialogo.isVisible(), timeout=10000)
    d = aba.dialogo
    assert not aba.preparando.isVisible()          # a camada de "preparando" saiu
    assert "Termômetro de exemplo" in d.windowTitle() and "v0.1.0" in d.windowTitle()
    d.senha.setText("errada")
    d.confirmar.click()
    assert d.isVisible() and d.erro.text() == "Senha incorreta. Restam 2 tentativa(s)."
    d.senha.setText(SENHA)
    d.confirmar.click()
    assert not d.isVisible()
    assert "Reinicie o Hidrolog para ativar" in pagina.aviso.texto.text()
    linha = {l["codigo"]: l for l in aba.tabela.linhas()}["termometro"]
    assert linha["estado"] == "instalado"
    assert aba.reiniciar.isVisible()
    estado = json.loads((dados_dir / "plugins" / "plugins.json").read_text())
    assert estado["plugins"]["termometro"]["versao"] == "0.1.0"
    acoes = [(l["acao"], l["resultado"]) for l in pagina.auditoria.tabela.linhas()]
    assert ("Importar", "recusado") in acoes and ("Importar", "ok") in acoes


def test_cancelar_e_desativar(usuarios, janela, qtbot, monkeypatch, estacao_interna):
    shell = entrar(janela, qtbot, "admin")
    pagina = shell.ir_para("configuracoes")
    aba = pagina.plugins
    monkeypatch.setattr(aba, "escolher_local", lambda: str(PLUGIN_TERMOMETRO))
    aba.importar_de("computador")
    esperar_tarefas(qtbot)
    qtbot.waitUntil(lambda: aba.dialogo is not None and aba.dialogo.isVisible(), timeout=10000)
    aba.dialogo.cancelar.click()
    assert "nada foi instalado" in pagina.aviso.texto.text()
    # desativar um plugin interno: pede senha; os dados ficam
    estacao = {l["codigo"]: l for l in aba.tabela.linhas()}["estacao"]["_info"]
    d = aba.alternar_ativo(estacao)
    d.senha.setText(SENHA)
    d.confirmar.click()
    linha = {l["codigo"]: l for l in aba.tabela.linhas()}["estacao"]
    assert "desativado ao reiniciar" in linha["detalhes"]
    assert aba.reiniciar.isVisible()
    servico.reativar_plugin(janela.ctx.usuario, "estacao", SENHA)


def test_plugin_incompativel_mostra_o_motivo(usuarios, janela, qtbot, monkeypatch, tmp_path):
    import shutil
    copia = tmp_path / "incompativel"
    shutil.copytree(PLUGIN_TERMOMETRO, copia, ignore=shutil.ignore_patterns("__pycache__"))
    toml = copia / "hidrolog-plugin.toml"
    toml.write_text(toml.read_text().replace('contrato = "1.x"', 'contrato = "2.x"'))
    shell = entrar(janela, qtbot, "admin")
    pagina = shell.ir_para("configuracoes")
    monkeypatch.setattr(pagina.plugins, "escolher_local", lambda: str(copia))
    pagina.plugins.importar_de("computador")
    esperar_tarefas(qtbot)
    qtbot.waitUntil(lambda: "contrato 2.x" in pagina.aviso.texto.text(), timeout=10000)
    assert "incompatível" in pagina.aviso.texto.text()
    assert pagina.plugins.dialogo is None
