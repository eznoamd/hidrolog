"""Contrato v1 dos plugins: descoberta, validacao e independencia do nucleo."""

import re
from dataclasses import replace
from pathlib import Path

import pytest

from app import servico
from app.nucleo import plugins
from hidrolog_nucleo.plugin import (
    VERSAO_CONTRATO, Campo, ErroManifesto, Manifesto, Regra, contrato_compativel, ler_manifesto,
)

RAIZ = Path(__file__).resolve().parents[2]


def test_nucleo_nao_importa_nenhum_sensor():
    """Backend (app, hidrolog_nucleo) e frontend (hidrolog) nao importam nenhum
    plugin (nem os de teste): nada de hidrolog_<sensor> nem sensor_teste."""
    padrao = re.compile(r"^\s*(from|import)\s+(hidrolog_(?!nucleo\b)\w+|sensor_teste)", re.MULTILINE)
    pastas = [RAIZ / "backend" / "app", RAIZ / "backend" / "hidrolog_nucleo", RAIZ / "frontend" / "hidrolog"]
    culpados = [str(p) for pasta in pastas for p in pasta.rglob("*.py") if padrao.search(p.read_text("utf-8"))]
    assert culpados == []


def test_sensor_de_teste_registrado(banco):
    situacao = {s.codigo: s for s in plugins.situacoes()}["estacao"]
    assert (situacao.origem, situacao.estado) == ("registro", "ativo")
    assert plugins.obter("estacao").manifesto == ler_manifesto(Path(__file__).parent / "sensor_estacao")
    assert "estacao" in {t.codigo for t in servico.listar_tipos_sensor()}


def test_contrato_compativel():
    assert VERSAO_CONTRATO.startswith("1.")
    assert contrato_compativel("1.x") and contrato_compativel("1.0")
    assert not contrato_compativel("2.x") and not contrato_compativel("1.99") and not contrato_compativel("x")


def test_plugin_incompativel_nao_e_registrado():
    falso = plugins.obter("falso")
    outro = replace(falso, manifesto=replace(falso.manifesto, codigo="outro", contrato="2.x"))
    with pytest.raises(ValueError, match="contrato 2.x incompativel"):
        plugins.registrar(outro)
    with pytest.raises(ValueError, match="ja existe"):
        plugins.registrar(replace(falso))


@pytest.mark.parametrize("dados,mensagem", [
    ({"codigo": "x"}, "faltam"),
    ({"codigo": "Com Espaco", "nome": "n", "versao": "1.0.0", "contrato": "1.x", "modulo": "m"}, "codigo invalido"),
    ({"codigo": "ok", "nome": "n", "versao": "1.0", "contrato": "1.x", "modulo": "m"}, "versao invalida"),
    ({"codigo": "ok", "nome": "n", "versao": "1.0.0", "contrato": "um", "modulo": "m"}, "contrato invalido"),
])
def test_manifesto_invalido(dados, mensagem):
    with pytest.raises(ErroManifesto, match=mensagem):
        Manifesto.de_dict(dados)


def test_campo_e_regra_declarativos():
    c = Campo("intervalo", "Intervalo", tipo="inteiro", unidade="s", minimo=10, maximo=3600)
    assert c.validar("120") == 120 and c.validar(None) is None
    for ruim in ("abc", 5, 3601, 1.5):
        with pytest.raises(ValueError):
            c.validar(ruim)
    with pytest.raises(ValueError):
        Regra("r", "regra sem funcao nem coluna", nivel="envio")
