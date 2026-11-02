"""Ingestao em tres camadas com formatos diferentes pelo mesmo nucleo (F1):
um CSV de muitas linhas (lido em fluxo) e dados + calibracao (com zip dentro
de zip), alem da arvore de arquivos e dos limites dela."""

import io
import json
import struct
import zipfile
from datetime import datetime, timedelta

import pytest
from sqlalchemy import func, select

from app import servico
from app.nucleo import paralelo
from app.nucleo.erros import EnvioRecusado, LimiteExcedido
from app.nucleo.extracao import Abertura
from tests.plugins_teste.calibrado import CalibradoLeitura
from tests.plugins_teste.csvlongo import PluvioLeitura

from .conftest import config_teste

N_LINHAS = 20_000
INICIO = datetime(2026, 1, 1)


def _csv(n=N_LINHAS, cabecalho="data_hora;pulsos", desloca=0) -> bytes:
    linhas = [cabecalho] + [f"{(INICIO + timedelta(minutes=i + desloca)):%Y-%m-%d %H:%M:%S};{i % 7}" for i in range(n)]
    return ("\n".join(linhas) + "\n").encode()


def _zip(itens) -> bytes:
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w", zipfile.ZIP_DEFLATED) as z:
        for nome, conteudo in itens:
            z.writestr(nome, conteudo)
    return saida.getvalue()


def _bin(inicio_s: int, n: int) -> bytes:
    return b"".join(struct.pack("<qh", inicio_s + 60 * i, i) for i in range(n))


# ------------------------------------------------------------------ CSV longo

@pytest.fixture
def pluvio(cadastro):
    return servico.criar_equipamento(cadastro, "testepluvio", "Pluviômetro 1")


def test_csv_de_muitas_linhas_em_fluxo(cadastro, pluvio, banco, tmp_path):
    # o CSV (~560 kB) passa do limite de leitura inteira (64 kB): so entra porque e lido em fluxo
    servico.iniciar(url=banco.url, config=config_teste(banco.url, max_arquivo_leitura=64 * 1024))
    pasta = tmp_path / "logger"
    pasta.mkdir()
    (pasta / "pulsos.csv").write_bytes(_csv())
    (pasta / "leia-me.txt").write_text("datalogger")
    eventos = []
    resumo = servico.importar_caminho(cadastro, pluvio.id, pasta, ao_progresso=lambda *a: eventos.append(a))
    assert (resumo.leituras, resumo.novas, resumo.duplicadas, resumo.ignorados) == (N_LINHAS, N_LINHAS, 0, 1)
    assert resumo.inicio == INICIO and resumo.fim == INICIO + timedelta(minutes=N_LINHAS - 1)
    assert ("interpretando", 1, 1) in eventos
    with banco.sessao() as sessao:
        assert sessao.scalar(select(func.count(PluvioLeitura.id))) == N_LINHAS
    # reimportar + um CSV que se sobrepoe na metade
    (pasta / "pulsos2.csv").write_bytes(_csv(n=1000, desloca=N_LINHAS - 500))
    resumo = servico.importar_caminho(cadastro, pluvio.id, pasta)
    assert (resumo.novas, resumo.duplicadas) == (500, N_LINHAS + 500)


def test_csv_sem_coluna_e_recusado(cadastro, pluvio):
    with pytest.raises(EnvioRecusado, match="pulsos"):
        servico.importar_arquivos(cadastro, pluvio.id, [("dados.csv", _csv(n=3, cabecalho="data_hora;chuva"))])
    with pytest.raises(EnvioRecusado, match="nenhum .csv"):
        servico.importar_arquivos(cadastro, pluvio.id, [("dados.txt", b"x")])
    assert servico.listar_envios(cadastro) == []


def test_fluxo_respeita_o_limite_total(cadastro, pluvio, banco):
    servico.iniciar(url=banco.url, config=config_teste(banco.url, max_descompactado=100_000))
    with pytest.raises(LimiteExcedido):
        servico.importar_arquivos(cadastro, pluvio.id, [("SD.zip", _zip([("pulsos.csv", _csv())]))])
    assert servico.listar_envios(cadastro) == []


# ------------------------------------------------------------------ dados + calibracao

@pytest.fixture
def calibrado(cadastro):
    return servico.criar_equipamento(cadastro, "testecalibrado", "Sensor calibrado 1")


def _envio_calibrado(cal={"fator": 2.0, "deslocamento": 0.5}) -> bytes:
    """zip dentro de zip: externo com calibracao.json + medicoes.zip (os .bin)."""
    interno = _zip([("a/1.bin", _bin(1_767_225_600, 50)), ("a/2.bin", _bin(1_767_225_600 + 3000, 50))])
    return _zip([("calibracao.json", json.dumps(cal)), ("medicoes.zip", interno), ("notas.md", "x")])


def test_dados_com_calibracao_e_zip_dentro_de_zip(cadastro, calibrado, banco):
    resumo = servico.importar_arquivos(cadastro, calibrado.id, [("envio.zip", _envio_calibrado())])
    assert (resumo.leituras, resumo.novas, resumo.ignorados) == (100, 100, 1)
    assert resumo.arquivos_recebidos == 4           # calibracao, 2 .bin (de dentro do zip interno) e notas
    with banco.sessao() as sessao:
        bruto, valor = sessao.execute(select(CalibradoLeitura.bruto, CalibradoLeitura.valor)
                                      .order_by(CalibradoLeitura.tempo).limit(2).offset(1)).first()
        assert (bruto, valor) == (1, 2.5)          # 1 * 2.0 + 0.5
    assert servico.importar_arquivos(cadastro, calibrado.id, [("envio.zip", _envio_calibrado())]).duplicadas == 100


def test_calibracao_vai_para_os_processos(cadastro, calibrado, banco, monkeypatch):
    """Leitura em paralelo: a calibracao do reconhecer chega nos processos (Unidade.dados)."""
    original = paralelo.mapear_lotes
    monkeypatch.setattr(paralelo, "processos", 2)
    monkeypatch.setattr(paralelo, "mapear_lotes",
                        lambda f, itens, **kw: original(f, itens, tamanho_lote=1, minimo_paralelo=1))
    try:
        resumo = servico.importar_arquivos(cadastro, calibrado.id,
                                           [("envio.zip", _envio_calibrado({"fator": 3, "deslocamento": 0}))])
    finally:
        paralelo.encerrar()
    assert resumo.novas == 100
    with banco.sessao() as sessao:
        assert sessao.scalar(select(func.max(CalibradoLeitura.valor))) == 49 * 3


def test_sem_calibracao_e_recusado(cadastro, calibrado):
    with pytest.raises(EnvioRecusado, match="calibracao.json"):
        servico.importar_arquivos(cadastro, calibrado.id, [("x.zip", _zip([("1.bin", _bin(0, 3))]))])


def test_unidade_com_problema_nao_derruba_o_envio(cadastro, calibrado):
    envio = _zip([("calibracao.json", '{"fator": 1}'), ("ok.bin", _bin(0, 5)), ("quebrado.bin", b"\x00" * 7)])
    resumo = servico.importar_arquivos(cadastro, calibrado.id, [("e.zip", envio)])
    assert (resumo.novas, resumo.ignorados) == (5, 1)
    assert any("quebrado.bin" in a for a in resumo.avisos)


def test_sugerir_tipo(cadastro, tmp_path):
    caminho = tmp_path / "envio.zip"
    caminho.write_bytes(_envio_calibrado())
    assert [t.codigo for t in servico.sugerir_tipo([caminho])] == ["testecalibrado"]
    assert [t.codigo for t in servico.sugerir_tipo([("p.csv", _csv(n=2))])] == ["testepluvio"]


# ------------------------------------------------------------------ arvore

def test_arvore_zip_em_zip_ate_dois_niveis(banco):
    nivel3 = _zip([("fundo.txt", "x")])
    nivel2 = _zip([("meio.txt", "y"), ("n3.zip", nivel3)])
    externo = _zip([("topo.txt", "z"), ("n2.zip", nivel2)])
    with Abertura(config_teste(banco.url)) as ab:
        ab.adicionar_parte("externo.zip", io.BytesIO(externo))
        caminhos = sorted(a.caminho for a in ab.arvore)
        assert caminhos == ["n2.zip/meio.txt", "n2.zip/n3.zip", "topo.txt"]   # o 3o nivel nao e aberto
        assert ab.arvore.procurar("meio.txt").texto() == "y"


def test_arvore_path_traversal_no_zip_interno(banco):
    from app.nucleo.erros import ErroEnvio
    externo = _zip([("ok.zip", _zip([("../../fora.txt", "x")]))])
    with Abertura(config_teste(banco.url)) as ab, pytest.raises(ErroEnvio, match="nao permitido"):
        ab.adicionar_parte("externo.zip", io.BytesIO(externo))
