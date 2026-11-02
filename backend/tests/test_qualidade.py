"""Regras de qualidade e ocorrencias (F5): motor nos tres niveis, regras
declarativas e por funcao, parametros por equipamento, suspeitas, coluna de
qualidade na exportacao e regras que nunca alteram dados."""

import csv
import re
from dataclasses import replace
from datetime import datetime

import pytest
from sqlalchemy import select, text

from app import servico
from app.nucleo import plugins
from app.nucleo.erros import ErroPermissao, ErroValidacao
from hidrolog_nucleo.plugin import Ocorrencia, Regra

from .conftest import PASTA_DADOS

ARQ = PASTA_DADOS / "2026100804"


def _arquivo(nome: str, **campos) -> tuple[str, bytes]:
    """Um .txt da amostra com alguns campos trocados (ou acrescentados)."""
    texto = (ARQ / nome).read_text()
    for campo, valor in campos.items():
        linha = f"{campo}:{valor}"
        if re.search(rf"^{campo}:", texto, re.M):
            texto = re.sub(rf"^{campo}:.*$", linha, texto, flags=re.M)
        else:
            texto += linha + "\n"
    return nome, texto.encode()


def _dump(banco) -> list:
    with banco.engine.connect() as c:
        return [tuple(l) for l in c.execute(text("select * from estacao_leitura order by id"))]


def _codigos(cadastro, eq_id, **kw):
    return sorted(o.codigo_regra for o in servico.listar_ocorrencias(cadastro, eq_id, **kw))


def test_regras_de_leitura(cadastro, equipamento, banco, tmp_path):
    arquivos = [
        _arquivo("20261008040800.txt", status="1"),                       # status diferente de 0
        _arquivo("20261008041000.txt"),                                   # normal
        _arquivo("20261008041200.txt", chuva="450.0"),                    # chuva impossivel
        _arquivo("20261008041400.txt"),                                   # normal
    ]
    resumo = servico.importar_arquivos(cadastro, equipamento.id, arquivos)
    assert resumo.novas == 4 and resumo.ocorrencias >= 2
    leitura = servico.listar_ocorrencias(cadastro, equipamento.id, nivel="leitura")
    assert sorted((o.codigo_regra, o.severidade, str(o.tempo)) for o in leitura) == [
        ("chuva_impossivel", "suspeita", "2026-10-08 04:12:00"),
        ("status_sensor", "suspeita", "2026-10-08 04:08:00"),
    ]
    assert any("450,0" in o.mensagem or "450.0" in o.mensagem for o in leitura)
    suspeitas = servico.tempos_suspeitos(cadastro, equipamento.id)
    assert {t.strftime("%H:%M") for t in suspeitas} == {"04:08", "04:12"}
    # reimportar nao duplica ocorrencias (so as leituras novas passam pelas regras de leitura)
    servico.importar_arquivos(cadastro, equipamento.id, arquivos)
    assert len(servico.listar_ocorrencias(cadastro, equipamento.id, nivel="leitura")) == 2
    # exportacao leva a coluna de qualidade
    r = servico.exportar(cadastro, equipamento.id, None, None, "csv", tmp_path)
    with open(r.caminho, encoding="utf-8") as f:
        linhas = list(csv.DictReader(f))
    assert [l["qualidade"] for l in linhas] == ["status_sensor", "", "chuva_impossivel", ""]


def test_regras_de_envio_e_de_equipamento(cadastro, equipamento):
    servico.importar_caminho(cadastro, equipamento.id, PASTA_DADOS)       # 08/10 a 21/10, com lacunas
    abertas = servico.listar_ocorrencias(cadastro, equipamento.id)
    por_codigo = {o.codigo_regra: o for o in abertas}
    assert por_codigo["leituras_faltando"].nivel == "envio" and por_codigo["leituras_faltando"].severidade == "aviso"
    assert por_codigo["sem_dados"].nivel == "equipamento" and por_codigo["sem_dados"].severidade == "alerta"
    assert "sem dados há" in por_codigo["sem_dados"].mensagem
    resumo = servico.resumo_qualidade(cadastro)[equipamento.id]
    assert resumo.alertas == 1 and resumo.avisos >= 1
    # reavaliar nao duplica a ocorrencia aberta do equipamento
    servico.reavaliar_equipamentos()
    assert _codigos(cadastro, equipamento.id, nivel="equipamento") == ["sem_dados"]
    # com o limite maior, a condicao deixa de valer e a ocorrencia e resolvida sozinha
    servico.configurar_regra(cadastro, equipamento.id, "sem_dados", {"dias": 3650})
    assert _codigos(cadastro, equipamento.id, nivel="equipamento") == []
    resolvida = servico.listar_ocorrencias(cadastro, equipamento.id, abertas=False, nivel="equipamento")[0]
    assert resolvida.resolvida_em is not None and resolvida.resolvida_por == ""


def test_tensao_baixa(cadastro, equipamento):
    arquivos = [_arquivo(n, tensao="10.2") for n in ("20261008040800.txt", "20261008041000.txt")]
    servico.importar_arquivos(cadastro, equipamento.id, arquivos)
    assert "tensao_baixa" in _codigos(cadastro, equipamento.id, nivel="equipamento")


def test_parametros_por_equipamento(cadastro, leitor, equipamento):
    regras = {r.codigo: r for r in servico.listar_regras(leitor, equipamento.id)}
    assert set(regras) == {"status_sensor", "chuva_impossivel", "leituras_faltando", "sem_dados", "tensao_baixa"}
    assert regras["chuva_impossivel"].parametros == {"limite_mm_h": 300.0}
    with pytest.raises(ErroPermissao):
        servico.configurar_regra(leitor, equipamento.id, "chuva_impossivel", {"limite_mm_h": 40})
    with pytest.raises(ErroValidacao) as erro:
        servico.configurar_regra(cadastro, equipamento.id, "chuva_impossivel", {"limite_mm_h": "muito",
                                                                                       "outro": 1})
    assert set(erro.value.campos) == {"limite_mm_h", "outro"}
    r = servico.configurar_regra(cadastro, equipamento.id, "chuva_impossivel", {"limite_mm_h": "40,5"})
    assert r.parametros == {"limite_mm_h": 40.5} and r.alterada_por == "cad" and r.alterada_em is not None
    servico.configurar_regra(cadastro, equipamento.id, "status_sensor", ativa=False)
    servico.importar_arquivos(cadastro, equipamento.id, [_arquivo("20261008041600.txt", chuva="42.1", status="5")])
    codigos = _codigos(cadastro, equipamento.id, nivel="leitura")
    assert codigos == ["chuva_impossivel"]               # 42,1 mm/h > 40,5; a do status esta desligada
    # outro equipamento continua com o padrao
    outro = servico.criar_equipamento(cadastro, "estacao", "Estação 2")
    assert {r.codigo: r for r in servico.listar_regras(cadastro, outro.id)}["chuva_impossivel"].parametros \
        == {"limite_mm_h": 300.0}


def test_resolver_ocorrencia(cadastro, leitor, equipamento):
    servico.importar_arquivos(cadastro, equipamento.id, [_arquivo("20261008040800.txt", status="2")])
    o = servico.listar_ocorrencias(cadastro, equipamento.id, nivel="leitura")[0]
    with pytest.raises(ErroPermissao):
        servico.resolver_ocorrencia(leitor, o.id)
    feita = servico.resolver_ocorrencia(cadastro, o.id)
    assert feita.resolvida_por == "cad"
    assert servico.tempos_suspeitos(cadastro, equipamento.id) == set()     # resolvida: sai do destaque


def test_regras_nunca_alteram_dados(cadastro, equipamento, banco, monkeypatch):
    """Uma regra que tenta apagar e mudar leituras nao consegue: roda num
    savepoint desfeito. E as regras normais tambem nao mudam nada."""
    servico.importar_caminho(cadastro, equipamento.id, PASTA_DADOS)
    antes = _dump(banco)

    def maliciosa(ctx):
        ctx.sessao.execute(text("update estacao_leitura set chuva = -1"))
        ctx.sessao.execute(text("delete from estacao_leitura"))
        return [Ocorrencia("tentei apagar tudo")]

    estacao = plugins.obter("estacao")
    ruim = Regra("maliciosa", "tenta alterar dados", nivel="equipamento", severidade="alerta", funcao=maliciosa)
    monkeypatch.setitem(plugins._registro, "estacao", replace(estacao, regras=estacao.regras + (ruim,)))
    servico.reavaliar_equipamentos()
    servico.configurar_regra(cadastro, equipamento.id, "sem_dados", {"dias": 1})
    assert "maliciosa" in _codigos(cadastro, equipamento.id)
    for o in servico.listar_ocorrencias(cadastro, equipamento.id):
        servico.resolver_ocorrencia(cadastro, o.id)
    assert _dump(banco) == antes


def test_regra_com_defeito_nao_derruba_a_importacao(cadastro, equipamento, monkeypatch):
    estacao = plugins.obter("estacao")
    quebrada = Regra("quebrada", "levanta erro", nivel="leitura", funcao=lambda ctx: 1 / 0)
    monkeypatch.setitem(plugins._registro, "estacao", replace(estacao, regras=(quebrada,)))
    assert servico.importar_caminho(cadastro, equipamento.id, ARQ).novas == 7
