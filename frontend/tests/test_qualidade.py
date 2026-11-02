"""Qualidade na interface (F5): aba Qualidade, selo no cabeçalho e na lista de
equipamentos, cartão de alertas no Início e o filtro "ocultar suspeitas"."""

import re

from app import servico

from .conftest import PASTA_DADOS, entrar, importar


def _com_suspeita(master, eq_id):
    texto = (PASTA_DADOS / "2026100804" / "20261008041600.txt").read_text()
    texto = re.sub(r"^chuva:.*$", "chuva:450.0", texto, flags=re.M)      # chuva impossível
    servico.importar_arquivos(master, eq_id, [("20261008041600.txt", texto.encode())])
    importar(master, eq_id)


def test_aba_qualidade_e_selos(usuarios, master, janela, qtbot):
    eq = servico.criar_equipamento(master, "estacao", "Estação 1")
    _com_suspeita(master, eq.id)
    shell = entrar(janela, qtbot, "cad")
    inicio = shell.ir_para("inicio")
    assert inicio.alertas.isVisible()
    linha = inicio.tabela_alertas.linhas()[0]
    assert linha["nome"] == "Estação 1" and linha["alertas"] == 1 and linha["suspeitas"] == 1
    lista = shell.ir_para("equipamentos")
    assert lista.tabela.linhas()[0]["qualidade"] == ("1 alerta(s)", "erro")
    inicio._abrir_qualidade(linha)
    pagina = shell.area.currentWidget()
    assert pagina.abas.atual() == "qualidade"
    assert pagina.alertas.isVisible() and "alerta" in pagina.alertas.text()
    q = pagina.abas.widget("qualidade")
    codigos = {l["regra"] for l in q.tabela.linhas()}
    assert {"chuva_impossivel", "sem_dados", "leituras_faltando"} <= codigos
    regras = {l["_regra"].codigo: l for l in q.regras.linhas()}
    assert regras["chuva_impossivel"]["parametros"] == "limite_mm_h = 300"
    # ajustar uma regra (cadastro): fica registrado quem alterou
    d = q.abrir_regra(regras["sem_dados"]["_regra"])
    d.campos["dias"].setText("dez")
    d.botao_confirmar.click()
    assert d.isVisible() and d.campos["dias"].property("invalido") == "true"
    d.campos["dias"].setText("3650")
    d.botao_confirmar.click()
    assert not d.isVisible()
    regras = {l["_regra"].codigo: l for l in q.regras.linhas()}
    assert regras["sem_dados"]["alterada"].startswith("cad · ")
    assert "sem_dados" not in {l["regra"] for l in q.tabela.linhas()}     # resolvida sozinha
    # marcar como resolvida
    linha = next(l for l in q.tabela.linhas() if l["regra"] == "chuva_impossivel")
    q.tabela.tabela.selectRow(q.tabela.linhas().index(linha))
    q.resolver.click()
    assert "chuva_impossivel" not in {l["regra"] for l in q.tabela.linhas()}


def test_filtro_ocultar_suspeitas(usuarios, master, janela, qtbot):
    """As abas do plugin recebem as suspeitas e o filtro do cabeçalho."""
    eq = servico.criar_equipamento(master, "estacao", "Estação 1")
    _com_suspeita(master, eq.id)
    entrar(janela, qtbot, "ler")
    pagina = janela.ctx.abrir_equipamento(eq.id)
    aba = pagina.abas.ir_para("leituras")
    assert len(aba.leituras) == 12
    pagina.ocultar_suspeitas.setChecked(True)
    qtbot.waitUntil(lambda: len(aba.leituras) == 11, timeout=10000)     # a de 450 mm/h saiu
    assert all(l["chuva"] != 450.0 for l in aba.leituras)
    pagina.ocultar_suspeitas.setChecked(False)
    qtbot.waitUntil(lambda: len(aba.leituras) == 12, timeout=10000)
