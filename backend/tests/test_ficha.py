"""Ficha do equipamento (F4): campos comuns novos, atributos do plugin
validados no backend, campos preenchidos pelas leituras e migracao de atributos."""

from dataclasses import replace
from datetime import date

import pytest

from app import servico
from app.nucleo import plugins
from app.nucleo.erros import ErroValidacao
from hidrolog_nucleo.plugin import Campo

from .conftest import PASTA_DADOS


FICHA_EDITAVEL = (
    Campo("intervalo_esperado_s", "Intervalo esperado", tipo="inteiro", unidade="s", padrao=120,
          minimo=10, maximo=3600),
    Campo("altura_m", "Altura", tipo="decimal", unidade="m", minimo=0, maximo=50),
)


@pytest.fixture
def ficha_editavel(monkeypatch):
    """O plugin falso com uma ficha so de campos digitados."""
    monkeypatch.setitem(plugins._registro, "falso", replace(plugins.obter("falso"), ficha=FICHA_EDITAVEL))
    return "falso"


def test_ficha_com_campo_digitado_e_campos_das_leituras(cadastro):
    campos = {c.chave: c for c in servico.ficha_do_tipo("estacao")}
    assert set(campos) == {"intervalo_s", "firmware", "numero_serie_lido"}
    assert campos["intervalo_s"].origem is None
    assert campos["firmware"].origem == campos["numero_serie_lido"].origem == "leituras"
    eq = servico.criar_equipamento(cadastro, "estacao", "E1", latitude="-29,7", longitude=-53.71)
    assert eq.atributos == {"intervalo_s": 120} and eq.versao_ficha == 2      # so o padrao do digitado


def test_ficha_editavel_e_campos_comuns(cadastro, ficha_editavel):
    eq = servico.criar_equipamento(cadastro, ficha_editavel, "F1", latitude="-29,7", longitude=-53.71,
                                   altitude_m=95, instalado_em="15/03/2024", atributos={"altura_m": "1,5"})
    assert (eq.latitude, eq.longitude, eq.altitude_m, eq.instalado_em) == (-29.7, -53.71, 95.0, date(2024, 3, 15))
    assert eq.atributos == {"intervalo_esperado_s": 120, "altura_m": 1.5}   # padrao + digitado
    eq = servico.alterar_equipamento(cadastro, eq.id, atributos={"intervalo_esperado_s": 60}, latitude=None)
    assert eq.atributos == {"intervalo_esperado_s": 60, "altura_m": 1.5} and eq.latitude is None
    assert eq.longitude == -53.71                              # nao passado: nao muda


def test_ficha_v1_perde_a_altura():
    from sensor_teste.ficha import migrar_atributos

    antigos = {"intervalo_s": 60, "altura_m": 1.2, "firmware": "2.11.6"}
    assert migrar_atributos(dict(antigos), 1) == {"intervalo_s": 60, "firmware": "2.11.6"}
    assert migrar_atributos(dict(antigos), 2) == antigos


@pytest.mark.parametrize("argumentos,campo", [
    (dict(latitude=95), "latitude"),
    (dict(longitude="leste"), "longitude"),
    (dict(instalado_em="31/02/2024"), "instalado_em"),
    (dict(instalado_em="01/01/2999"), "instalado_em"),
    (dict(atributos={"intervalo_esperado_s": 5}), "intervalo_esperado_s"),
    (dict(atributos={"intervalo_esperado_s": "dois minutos"}), "intervalo_esperado_s"),
    (dict(atributos={"cor": "azul"}), "cor"),
])
def test_valores_invalidos_rejeitados_pelo_backend(cadastro, ficha_editavel, argumentos, campo):
    with pytest.raises(ErroValidacao) as erro:
        servico.criar_equipamento(cadastro, ficha_editavel, "F1", **argumentos)
    assert campo in erro.value.campos
    assert servico.listar_equipamentos(cadastro) == []


def test_campos_somente_leitura_vem_das_leituras(cadastro):
    eq = servico.criar_equipamento(cadastro, "estacao", "E1", atributos={"firmware": "digitado"})
    assert "firmware" not in eq.atributos                     # nao editavel: o digitado e ignorado
    novo = (PASTA_DADOS / "2026100804" / "20261008041600.txt").read_bytes() + b"serie:450994\nfirmware:2.11.6\n"
    servico.importar_arquivos(cadastro, eq.id, [("20261008041600.txt", novo)])
    eq = servico.obter_equipamento(cadastro, eq.id)
    assert eq.atributos["firmware"] == "2.11.6" and eq.atributos["numero_serie_lido"] == "450994"
    # dados sem esses campos nao apagam o que ja se sabe
    servico.importar_caminho(cadastro, eq.id, PASTA_DADOS / "2026101417")
    assert servico.obter_equipamento(cadastro, eq.id).atributos["firmware"] == "2.11.6"


def test_migracao_de_atributos_quando_a_ficha_muda(cadastro, monkeypatch):
    falso = plugins.obter("falso")
    v1 = replace(falso, ficha=(Campo("altura_cm", "Altura", tipo="decimal", unidade="cm"),), versao_ficha=1)
    monkeypatch.setitem(plugins._registro, "falso", v1)
    eq = servico.criar_equipamento(cadastro, "falso", "F1", atributos={"altura_cm": 150})
    v2 = replace(falso, ficha=(Campo("altura_m", "Altura", tipo="decimal", unidade="m"),), versao_ficha=2,
                 migrar_atributos=lambda a, versao: {"altura_m": a.pop("altura_cm") / 100} if versao < 2 else a)
    monkeypatch.setitem(plugins._registro, "falso", v2)
    assert servico.migrar_atributos() == 1
    eq = servico.obter_equipamento(cadastro, eq.id)
    assert (eq.atributos, eq.versao_ficha) == ({"altura_m": 1.5}, 2)


def _lacunas(cadastro, eq_id):
    return [o for o in servico.listar_ocorrencias(cadastro, eq_id) if o.codigo_regra == "leituras_faltando"]


def test_regra_de_envio_usa_o_campo_da_ficha(cadastro):
    """A regra de lacunas usa o intervalo digitado na ficha (padrao 120 s)."""
    pasta = PASTA_DADOS / "2026100804"
    nomes = ["20261008040800.txt", "20261008041000.txt", "20261008041400.txt"]   # buraco de 4 min antes da 3a
    padrao = servico.criar_equipamento(cadastro, "estacao", "Intervalo padrão")
    servico.importar_arquivos(cadastro, padrao.id, [(n, (pasta / n).read_bytes()) for n in nomes])
    [o] = _lacunas(cadastro, padrao.id)
    assert "1 leitura(s) faltando" in o.mensagem and "intervalo de 120 s" in o.mensagem
    curto = servico.criar_equipamento(cadastro, "estacao", "Intervalo curto", atributos={"intervalo_s": 60})
    servico.importar_arquivos(cadastro, curto.id, [(n, (pasta / n).read_bytes()) for n in nomes])
    [o] = _lacunas(cadastro, curto.id)
    assert "4 leitura(s) faltando" in o.mensagem and "intervalo de 60 s" in o.mensagem
