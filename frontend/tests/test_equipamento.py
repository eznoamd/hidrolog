"""Página do equipamento: as abas do plugin (aqui, a do sensor de teste) e as
comuns, o período no cabeçalho, atualização após importar e os Recentes."""

from datetime import date

from app import servico
from design.componentes import SeletorEquipamentoPeriodo

from .conftest import VALIDAS, entrar, importar


def test_abas_do_plugin_e_comuns(usuarios, master, janela, qtbot):
    eq = servico.criar_equipamento(master, "estacao", "Estação 1", numero_serie="450123", local="Telhado")
    importar(master, eq.id)
    shell = entrar(janela, qtbot, "ler")
    pagina = janela.ctx.abrir_equipamento(eq.id)
    assert pagina.titulo.text() == "Estação 1"
    assert pagina.subtitulo.text() == "Estação de teste · nº 450123 · Telhado"
    assert pagina.abas.titulos() == ["Leituras", "Qualidade", "Envios", "Exportar", "Cadastro"]   # leitura: sem Importar
    assert pagina.periodo.valores() == (date(2026, 10, 8), date(2026, 10, 21))
    aba = pagina.abas.ir_para("leituras")
    assert len(aba.leituras) == VALIDAS                         # 13 lidas, 1 corrompida fora
    assert not aba.findChildren(SeletorEquipamentoPeriodo)       # nenhum seletor dentro da aba
    assert "equipamento.%d" % eq.id in shell._secoes["recentes"].paginas[0].chave


def test_periodo_vale_para_as_abas(usuarios, master, janela, qtbot):
    eq = servico.criar_equipamento(master, "estacao", "Estação 1")
    importar(master, eq.id)
    entrar(janela, qtbot, "admin")
    pagina = janela.ctx.abrir_equipamento(eq.id)
    aba = pagina.abas.ir_para("leituras")
    pagina.definir_periodo(date(2026, 10, 1), date(2026, 10, 2))
    qtbot.waitUntil(lambda: aba.leituras == [], timeout=5000)
    pagina.definir_periodo(date(2026, 10, 8), date(2026, 10, 8))
    qtbot.waitUntil(lambda: len(aba.leituras) == 7, timeout=5000)
    pagina.periodo_completo()
    qtbot.waitUntil(lambda: len(aba.leituras) == VALIDAS, timeout=5000)


def test_importacao_atualiza_a_pagina(usuarios, master, janela, qtbot):
    eq = servico.criar_equipamento(master, "estacao", "Estação 1")
    entrar(janela, qtbot, "cad")
    pagina = janela.ctx.abrir_equipamento(eq.id)
    aba = pagina.abas.ir_para("leituras")
    assert aba.leituras == []
    importar(master, eq.id)
    janela.ctx.dados_alterados.emit("envios")
    qtbot.waitUntil(lambda: len(aba.leituras) == VALIDAS, timeout=10000)
    assert pagina.periodo.valores() == (date(2026, 10, 8), date(2026, 10, 21))
    envios = pagina.abas.ir_para("envios")
    assert len(envios.tabela.linhas()) == 1


def test_abas_comuns(usuarios, master, janela, qtbot):
    eq = servico.criar_equipamento(master, "estacao", "Estação 1", numero_serie="450123")
    shell = entrar(janela, qtbot, "cad")
    pagina = janela.ctx.abrir_equipamento(eq.id)
    imp = pagina.abas.ir_para("importar")
    assert imp.equipamento.currentData() == eq.id and not imp.equipamento.isEnabled()
    exp = pagina.abas.ir_para("exportar")
    assert exp.seletor.equipamento.currentData() == eq.id and exp.formato.count() == 2
    cad = pagina.abas.ir_para("cadastro")
    assert cad.valores_sensor["Nº de série registrado"] == "450123" and cad.editar.isVisible()
    d = cad.abrir_edicao()
    d.nome.setText("Estação renomeada")
    d.botao_confirmar.click()
    qtbot.waitUntil(lambda: pagina.titulo.text() == "Estação renomeada", timeout=5000)
    assert shell._paginas["equipamento.%d" % eq.id].botao.text() == "Estação renomeada"


def test_recentes_guardados_por_usuario(usuarios, master, janela, qtbot):
    eqs = [servico.criar_equipamento(master, "estacao", f"Estação {i}") for i in range(7)]
    entrar(janela, qtbot, "ler")
    for eq in eqs:
        janela.ctx.abrir_equipamento(eq.id)
    recentes = [p.titulo for p in janela.shell._secoes["recentes"].paginas]
    assert recentes == ["Estação 6", "Estação 5", "Estação 4", "Estação 3", "Estação 2"]
    janela.encerrar_sessao()
    shell = entrar(janela, qtbot, "ler")
    assert [p.titulo for p in shell._secoes["recentes"].paginas] == recentes
