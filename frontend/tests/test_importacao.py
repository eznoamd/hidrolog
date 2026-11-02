"""Importação pela tela (numa thread), resumo exibido e deduplicação ao reimportar."""

import shutil

from PySide6.QtCore import Qt

from app import servico

from .conftest import N_LEITURAS, PASTA_DADOS, entrar, esperar_tarefas


def preparar(usuarios, master, janela, qtbot):
    eq = servico.criar_equipamento(master, "estacao", "Estação teste", numero_serie="450123")
    shell = entrar(janela, qtbot, "cad")
    pagina = shell.ir_para("importacao")
    return eq, pagina


def importar_pela_tela(pagina, qtbot, caminho):
    assert pagina.area.definir_caminho(str(caminho))
    assert pagina.importar.isEnabled()
    qtbot.mouseClick(pagina.importar, Qt.MouseButton.LeftButton)
    assert not pagina.importar.isEnabled()          # ocupado enquanto a thread trabalha
    esperar_tarefas(qtbot)
    qtbot.waitUntil(lambda: pagina.painel.resumo.isVisible(), timeout=5000)
    return pagina.ultimo_resumo


def test_importa_pasta_e_mostra_resumo(usuarios, master, janela, qtbot, tmp_path):
    eq, pagina = preparar(usuarios, master, janela, qtbot)
    assert pagina.equipamento.currentData() == eq.id
    progresso = []
    pagina.tarefa = None
    original = pagina._progresso
    pagina._progresso = lambda *a: (progresso.append(a), original(*a))
    sd = tmp_path / "SD"
    shutil.copytree(PASTA_DADOS, sd)
    (sd / "estacao_erros.log").write_text("log\n")
    r = importar_pela_tela(pagina, qtbot, sd)
    assert r.novas == N_LEITURAS and r.duplicadas == 0 and r.corrompidas == 1 and r.ignorados == 1
    painel = pagina.painel
    assert painel.titulo.text() == "Importação concluída"
    assert painel.c_novas.valor.text() == "13"
    assert painel.c_corr.valor.text() == "1"
    assert painel.c_ign.valor.text() == "1"
    assert painel.periodo.text() == "08/10/2026 04:08 – 21/10/2026 16:00"
    assert "corrompida" in painel.aviso.texto.text()
    assert pagina.avisos.isVisible()                  # lista dos ignorados
    inicio = janela.shell.ir_para("inicio")
    assert inicio.c_leituras.valor.text() == "13"
    assert [l["nome"] for l in inicio.equipamentos.linhas()] == ["Estação teste"]
    assert {p[0] for p in progresso} >= {"lendo", "interpretando"}
    assert pagina.importar.isEnabled()
    # o histórico mostra o envio
    hist = janela.shell.ir_para("historico")
    linhas = hist.tabela.linhas()
    assert len(linhas) == 1 and linhas[0]["novas"] == N_LEITURAS and linhas[0]["usuario"] == "cad"
    d = hist.abrir_detalhe(linhas[0])
    assert d is not None and d.isVisible()
    d.accept()


def test_reimportar_nao_duplica(usuarios, master, janela, qtbot):
    eq, pagina = preparar(usuarios, master, janela, qtbot)
    importar_pela_tela(pagina, qtbot, PASTA_DADOS)
    r = importar_pela_tela(pagina, qtbot, PASTA_DADOS)    # 2ª vez: refaz a lista de avisos
    assert r.novas == 0 and r.duplicadas == N_LEITURAS
    assert pagina.painel.c_novas.valor.text() == "0"
    assert pagina.painel.c_dup.valor.text() == "13"
    assert "Nenhuma leitura nova" in pagina.painel.aviso.texto.text()
    assert len(servico.listar_envios(master)) == 2


def test_cancelar_importacao(usuarios, master, janela, qtbot):
    eq, pagina = preparar(usuarios, master, janela, qtbot)
    pagina.area.definir_caminho(str(PASTA_DADOS))
    pagina.iniciar_importacao()
    pagina.tarefa.cancelar()       # cancela antes do primeiro aviso de progresso
    esperar_tarefas(qtbot)
    assert pagina.painel.titulo.text() == "Importação cancelada"
    assert servico.listar_envios(master) == []


def test_rar_sem_programa_tem_instrucao(usuarios, master, janela, qtbot):
    from app.nucleo.erros import ErroRarSemFerramenta
    eq, pagina = preparar(usuarios, master, janela, qtbot)
    pagina._falhou(ErroRarSemFerramenta("SD.rar: nenhum programa"))
    assert "sudo apt install unar" in pagina.painel.aviso.texto.text()


def test_arquivo_nao_aceito(usuarios, master, janela, qtbot, tmp_path):
    eq, pagina = preparar(usuarios, master, janela, qtbot)
    ruim = tmp_path / "dados.7z"
    ruim.write_bytes(b"x")
    assert not pagina.area.definir_caminho(str(ruim))
    assert not pagina.importar.isEnabled()
