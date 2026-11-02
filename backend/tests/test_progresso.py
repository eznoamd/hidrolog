"""ao_progresso de importar_caminho/importar_arquivos e existe_master()."""

import pytest
from sqlalchemy import func, select

from app import servico
from app.nucleo import paralelo
from sensor_teste.dados import EstacaoLeitura
from tests.conftest import N_ARQUIVOS, PASTA_DADOS


def test_existe_master(banco):
    assert servico.existe_master() is False


def test_existe_master_depois_de_criar(master):
    assert servico.existe_master() is True


def test_progresso_da_importacao(cadastro, equipamento, pasta_sd):
    eventos = []
    resumo = servico.importar_caminho(cadastro, equipamento.id, pasta_sd,
                                      ao_progresso=lambda *a: eventos.append(a))
    etapas = [e[0] for e in eventos]
    assert etapas[0] == "lendo" and etapas[-1] == "concluido"
    # as etapas vem em ordem: lendo... interpretando... concluido
    assert etapas == sorted(etapas, key=["lendo", "interpretando", "concluido"].index)
    lendo = [e for e in eventos if e[0] == "lendo"]
    assert lendo[-1][1] == resumo.arquivos_recebidos and lendo[-1][2] is None
    interpretando = [e for e in eventos if e[0] == "interpretando"]
    assert interpretando[0][1:] == (0, N_ARQUIVOS)
    assert interpretando[-1][1:] == (N_ARQUIVOS, N_ARQUIVOS)
    assert eventos[-1] == ("concluido", resumo.leituras, resumo.leituras)


def test_progresso_por_lotes_em_paralelo(cadastro, equipamento, pasta_sd, monkeypatch):
    """Com o pool, cada lote pronto avisa; o resultado e o mesmo."""
    monkeypatch.setattr(paralelo, "processos", 2)
    original = paralelo.mapear_lotes
    monkeypatch.setattr(paralelo, "mapear_lotes",
                        lambda f, itens, **kw: original(f, itens, tamanho_lote=4, minimo_paralelo=1))
    eventos = []
    try:
        resumo = servico.importar_caminho(cadastro, equipamento.id, pasta_sd,
                                          ao_progresso=lambda *a: eventos.append(a))
    finally:
        paralelo.encerrar()
    feitos = [e[1] for e in eventos if e[0] == "interpretando"]
    assert feitos == [0, 4, 8, 12, 13]
    assert resumo.leituras == N_ARQUIVOS and resumo.novas == N_ARQUIVOS


def test_excecao_no_progresso_cancela_sem_gravar(cadastro, equipamento, banco):
    class Cancelada(Exception):
        pass

    def cancelar(etapa, feitos, total):
        if etapa == "interpretando" and feitos > 0:
            raise Cancelada()

    with pytest.raises(Cancelada):
        servico.importar_caminho(cadastro, equipamento.id, PASTA_DADOS, ao_progresso=cancelar)
    with banco.sessao() as sessao:
        assert sessao.scalar(select(func.count(EstacaoLeitura.id))) == 0
    assert servico.listar_envios(cadastro) == []
