"""Exportação CSV pela tela, numa thread, com o resumo."""

import csv

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog

from app import servico

from .conftest import VALIDAS, entrar, esperar_tarefas, importar


def test_exporta_csv(usuarios, master, janela, qtbot, tmp_path, monkeypatch):
    eq = servico.criar_equipamento(master, "estacao", "Estação 1", numero_serie="450123")
    importar(master, eq.id)
    shell = entrar(janela, qtbot, "ler")            # leitura também exporta
    pagina = shell.ir_para("exportacao")
    assert pagina.seletor.equipamento.currentData() == eq.id
    i = pagina.formato.findText("CSV", Qt.MatchFlag.MatchStartsWith)
    assert i >= 0
    pagina.formato.setCurrentIndex(i)
    assert pagina.nome_sugerido() == "Estação_1.csv"
    destino = tmp_path / "saida"
    destino.mkdir()
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        staticmethod(lambda *a, **k: (str(destino / "exportado"), "")))
    qtbot.mouseClick(pagina.exportar, Qt.MouseButton.LeftButton)
    esperar_tarefas(qtbot)
    qtbot.waitUntil(lambda: pagina.resultado.isVisible(), timeout=5000)
    arquivo = destino / "exportado.csv"
    assert pagina.ultimo.caminho == str(arquivo)
    with open(arquivo, encoding="utf-8") as f:
        linhas = list(csv.DictReader(f))
    assert len(linhas) == VALIDAS and "chuva_mm_h" in linhas[0]      # a corrompida não sai
    assert pagina.r_valores["leituras"].text() == "12"
    assert pagina.r_valores["periodo"].text() == "08/10/2026 04:08 – 21/10/2026 16:00"
    assert "12 leituras exportadas" in pagina.aviso.texto.text()


def test_exporta_um_periodo(usuarios, master, janela, qtbot, tmp_path):
    from PySide6.QtCore import QDate
    eq = servico.criar_equipamento(master, "estacao", "Estação 1")
    importar(master, eq.id)
    shell = entrar(janela, qtbot, "admin")
    pagina = shell.ir_para("exportacao")
    pagina.tudo.setChecked(False)
    pagina.seletor.inicio.setDate(QDate(2026, 10, 8))
    pagina.seletor.fim.setDate(QDate(2026, 10, 8))
    pagina.exportar_para(str(tmp_path / "dia.csv"))
    esperar_tarefas(qtbot)
    qtbot.waitUntil(lambda: pagina.resultado.isVisible(), timeout=5000)
    assert pagina.ultimo.leituras == 7
