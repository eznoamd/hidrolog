"""Exportacao pela camada de servico: formatos do plugin, periodo, coluna de
qualidade, nome do arquivo, metadados da instalacao e nada pela metade."""

import csv
import json
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import pytest

from app import servico
from app.nucleo import plugins
from app.nucleo.erros import ErroPermissao, ErroServico

from .conftest import N_ARQUIVOS, PASTA_DADOS

VALIDAS = N_ARQUIVOS - 1        # a corrompida nao e exportada


@pytest.fixture
def com_dados(cadastro, equipamento):
    servico.importar_caminho(cadastro, equipamento.id, PASTA_DADOS)
    return equipamento


def test_formatos(com_dados):
    assert [f.codigo for f in servico.listar_formatos_exportacao(com_dados.id)] == ["csv", "json"]


def test_csv(leitor, com_dados, tmp_path):
    resumo = servico.exportar(leitor, com_dados.id, None, None, "csv", tmp_path)
    assert resumo.leituras == VALIDAS and resumo.tamanho_bytes > 0
    assert resumo.caminho.endswith(".csv")
    with open(resumo.caminho, encoding="utf-8", newline="") as f:
        linhas = list(csv.DictReader(f))
    assert len(linhas) == VALIDAS
    assert linhas[0]["tempo"] == "2026-10-08T04:08:00" and float(linhas[0]["chuva_mm_h"]) == 0.0
    assert "20261011051200.txt" not in {l["arquivo"] for l in linhas}


def test_json_com_metadados(leitor, com_dados, tmp_path):
    destino = tmp_path / "saida.json"
    resumo = servico.exportar(leitor, com_dados.id, None, None, "json", destino)
    assert resumo.caminho == str(destino) and resumo.leituras == VALIDAS
    dados = json.loads(destino.read_text(encoding="utf-8"))
    assert dados["equipamento"] == "Estação teste" and dados["numero_serie"] == "450123"
    assert dados["institution"] == ""                       # instalação sem pasta de marca
    assert [l["tempo"] for l in dados["leituras"]] == sorted(l["tempo"] for l in dados["leituras"])


def test_filtro_de_periodo(leitor, com_dados, tmp_path):
    resumo = servico.exportar(leitor, com_dados.id, datetime(2026, 10, 8), datetime(2026, 10, 8, 4, 12),
                              "json", tmp_path)
    assert resumo.leituras == 3
    assert (resumo.inicio, resumo.fim) == (datetime(2026, 10, 8, 4, 8), datetime(2026, 10, 8, 4, 12))
    assert resumo.caminho.endswith("_202610080000_202610080412.json")
    vazio = servico.exportar(leitor, com_dados.id, datetime(2030, 1, 1), None, "csv", tmp_path / "v.csv")
    assert vazio.leituras == 0 and vazio.inicio is None


def test_exportar_erros(leitor, com_dados, tmp_path, monkeypatch):
    saida = tmp_path / "saida"
    saida.mkdir()
    with pytest.raises(ErroServico, match="formato"):
        servico.exportar(leitor, com_dados.id, None, None, "xlsx", saida)
    with pytest.raises(ErroServico, match="pasta"):
        servico.exportar(leitor, com_dados.id, None, None, "csv", saida / "nao" / "existe.csv")

    def falha_no_meio(sessao, equipamento_id, inicio, fim, formato, destino, contexto):
        Path(destino).write_text("pela metade")
        raise RuntimeError("disco cheio")

    estacao = plugins.obter("estacao")
    monkeypatch.setitem(plugins._registro, "estacao",
                        replace(estacao, exportacao=replace(estacao.exportacao, exportar=falha_no_meio)))
    with pytest.raises(RuntimeError):
        servico.exportar(leitor, com_dados.id, None, None, "csv", saida / "a.csv")
    assert list(saida.iterdir()) == []      # nada pela metade


def test_institution_vem_da_marca_da_instalacao(leitor, com_dados, tmp_path, monkeypatch):
    marca = tmp_path / "marca"
    marca.mkdir()
    (marca / "marca.toml").write_text('[laboratorio]\nsigla = "LAB"\nnome = "Laboratório X"\n'
                                      '[instituicao]\nsigla = "UNIV"\n', encoding="utf-8")
    monkeypatch.setenv("HIDROLOG_MARCA_DIR", str(marca))
    destino = tmp_path / "saida.json"
    servico.exportar(leitor, com_dados.id, None, None, "json", destino)
    assert json.loads(destino.read_text(encoding="utf-8"))["institution"] == "Laboratório X (LAB); UNIV"
