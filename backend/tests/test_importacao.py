"""Importacao pela camada de servico, sem HTTP."""

import io
import zipfile
from datetime import datetime

import pytest
from sqlalchemy import select

from app import servico
from app.nucleo.erros import EnvioRecusado, ErroEnvio, ErroRarSemFerramenta, LimiteExcedido
from app.nucleo import extracao
from sensor_teste import consultas
from sensor_teste.dados import EstacaoLeitura

from .conftest import N_ARQUIVOS, PASTA_DADOS, config_teste
from .rar import criar_rar


def _confere_sd(resumo, canal, tipo):
    assert resumo.canal == canal and resumo.tipo == tipo
    assert resumo.arquivos_recebidos == N_ARQUIVOS + 2
    assert resumo.ignorados == 2
    assert resumo.leituras == N_ARQUIVOS
    assert resumo.validas == N_ARQUIVOS - 1 and resumo.corrompidas == 1
    assert resumo.novas == N_ARQUIVOS and resumo.duplicadas == 0
    assert str(resumo.inicio) == "2026-10-08 04:08:00" and str(resumo.fim) == "2026-10-21 16:00:00"
    assert "estacao_erros.log" in resumo.arquivos_ignorados


def test_importar_pasta_local(cadastro, equipamento, pasta_sd):
    _confere_sd(servico.importar_caminho(cadastro, equipamento.id, pasta_sd), "local", "pasta")


def test_importar_zip_com_caminhos_do_windows(cadastro, equipamento, zip_sd):
    with zipfile.ZipFile(zip_sd) as z:
        assert any("\\" in n for n in z.namelist())
    resumo = servico.importar_caminho(cadastro, equipamento.id, zip_sd)
    _confere_sd(resumo, "local", "zip")
    assert "Logger/Backup/logger_backup.csv" in resumo.arquivos_ignorados


def test_importar_zip_em_memoria_como_upload(cadastro, equipamento, zip_sd):
    resumo = servico.importar_arquivos(cadastro, equipamento.id, [("SD.zip", zip_sd.read_bytes())])
    _confere_sd(resumo, "upload", "zip")


def test_importar_pasta_de_medicao(cadastro, equipamento):
    resumo = servico.importar_caminho(cadastro, equipamento.id, PASTA_DADOS / "2026100804")
    assert (resumo.leituras, resumo.novas, resumo.ignorados) == (7, 7, 0)


def test_importar_txt_soltos_em_memoria(cadastro, equipamento):
    arquivos = [(p.name, p.read_bytes()) for p in sorted((PASTA_DADOS / "2026101417").glob("*.txt"))]
    resumo = servico.importar_arquivos(cadastro, equipamento.id, arquivos)
    assert resumo.tipo == "arquivos" and resumo.novas == 3


def test_reenvio_nao_duplica(cadastro, equipamento, zip_sd, pasta_sd):
    servico.importar_caminho(cadastro, equipamento.id, zip_sd)
    for origem in (zip_sd, pasta_sd):
        resumo = servico.importar_caminho(cadastro, equipamento.id, origem)
        assert resumo.novas == 0 and resumo.duplicadas == N_ARQUIVOS
    assert consultas.resumo_leituras(cadastro, equipamento.id).leituras == N_ARQUIVOS
    assert len(servico.listar_envios(cadastro, equipamento.id)) == 3


def test_envio_que_se_sobrepoe(cadastro, equipamento, pasta_sd):
    servico.importar_caminho(cadastro, equipamento.id, PASTA_DADOS / "2026100804")
    resumo = servico.importar_caminho(cadastro, equipamento.id, pasta_sd)
    assert (resumo.novas, resumo.duplicadas) == (N_ARQUIVOS - 7, 7)


def test_deduplicacao_e_por_equipamento(cadastro, equipamento, pasta_sd):
    outro = servico.criar_equipamento(cadastro, "estacao", "Estação 2")
    servico.importar_caminho(cadastro, equipamento.id, pasta_sd)
    resumo = servico.importar_caminho(cadastro, outro.id, pasta_sd)
    assert resumo.novas == N_ARQUIVOS
    assert consultas.resumo_leituras(cadastro, outro.id).leituras == N_ARQUIVOS


def test_mesma_leitura_repetida_no_envio(cadastro, equipamento):
    arq = PASTA_DADOS / "2026102116" / "20261021160000.txt"
    resumo = servico.importar_arquivos(cadastro, equipamento.id, [
        ("a/20261021160000.txt", arq.read_bytes()), ("b/20261021160000.txt", arq.read_bytes())])
    assert (resumo.novas, resumo.duplicadas) == (1, 1)


def test_arquivos_ignorados(cadastro, equipamento):
    arq = PASTA_DADOS / "2026102116" / "20261021160000.txt"
    resumo = servico.importar_arquivos(cadastro, equipamento.id, [
        ("estacao_erros.log", b"x"),
        ("logger_backup.csv", b"x"),
        ("2026100804.txt", b"x"),
        ("20261399999999.txt", b"chuva:0\n"),                    # 14 digitos que nao sao data
        ("20261021160000.txt", arq.read_bytes()),
    ])
    assert (resumo.arquivos_recebidos, resumo.ignorados, resumo.leituras, resumo.novas) == (5, 4, 1, 1)


def test_envio_sem_leituras_do_sensor_e_recusado(cadastro, equipamento):
    """O plugin reconhece a estrutura: sem nenhuma leitura do sensor, o envio
    e recusado com o motivo (e nada e registrado)."""
    with pytest.raises(EnvioRecusado, match="AAAAMMDDHHMMSS"):
        servico.importar_arquivos(cadastro, equipamento.id, [
            ("estacao_erros.log", b"x"), ("logger_backup.csv", b"x"), ("20261399999999.txt", b"chuva:0\n")])
    assert servico.listar_envios(cadastro) == []


def test_corrompida_guardada_com_o_que_deu_para_ler(cadastro, equipamento, banco):
    servico.importar_caminho(cadastro, equipamento.id, PASTA_DADOS / "2026101105")
    with banco.sessao() as sessao:
        linha = sessao.scalar(select(EstacaoLeitura).where(EstacaoLeitura.arquivo == "20261011051200.txt"))
        assert linha.corrompido and linha.chuva is None and linha.temperatura is not None
    assert consultas.resumo_leituras(cadastro, equipamento.id).corrompidas == 1
    assert len(consultas.buscar_leituras(cadastro, equipamento.id)) == 1       # a corrompida fica de fora


def test_campos_opcionais(cadastro, equipamento, banco):
    """Leituras com e sem os campos opcionais (nº de série, firmware, intervalo)."""
    novos = b"serie:450123\nfirmware:2.11.6\nintervalo:120\n"
    pasta = PASTA_DADOS / "2026100804"
    servico.importar_arquivos(cadastro, equipamento.id, [
        ("20261008041600.txt", (pasta / "20261008041600.txt").read_bytes() + novos),
        ("20261008041800.txt", (pasta / "20261008041800.txt").read_bytes()),
    ])
    with banco.sessao() as sessao:
        novo, antigo = sessao.scalars(select(EstacaoLeitura).order_by(EstacaoLeitura.tempo)).all()
        assert (novo.numero_serie, novo.firmware, novo.intervalo) == ("450123", "2.11.6", 120)
        assert antigo.numero_serie is None and antigo.intervalo is None and antigo.chuva is not None


def test_aviso_numero_de_serie_diferente(cadastro, equipamento):
    texto = (PASTA_DADOS / "2026100804" / "20261008041600.txt").read_bytes() + b"serie:999999\n"
    resumo = servico.importar_arquivos(cadastro, equipamento.id, [("20261008041600.txt", texto)])
    assert resumo.avisos and "999999" in resumo.avisos[0]


def test_numero_de_serie_registrado_pela_primeira_importacao(cadastro):
    """Sem nº de série no cadastro, o da primeira importação que o trouxer fica
    registrado; a seguinte, com outro nº, gera o aviso de equipamento errado."""
    eq = servico.criar_equipamento(cadastro, "estacao", "Estação sem série")
    base = (PASTA_DADOS / "2026100804" / "20261008041600.txt").read_bytes()
    antigo = servico.importar_arquivos(cadastro, eq.id, [("20261008041400.txt", (PASTA_DADOS / "2026100804"
                                                          / "20261008041400.txt").read_bytes())])
    assert not antigo.avisos and servico.obter_equipamento(cadastro, eq.id).numero_serie is None
    resumo = servico.importar_arquivos(cadastro, eq.id, [("20261008041600.txt", base + b"serie:450994\n")])
    assert any("450994 registrado" in a for a in resumo.avisos)
    assert servico.obter_equipamento(cadastro, eq.id).numero_serie == "450994"
    outro = servico.importar_arquivos(cadastro, eq.id, [("20261008041800.txt", (PASTA_DADOS / "2026100804"
                                                         / "20261008041800.txt").read_bytes() + b"serie:999999\n")])
    assert any("999999" in a and "diferente do cadastrado" in a for a in outro.avisos)
    assert servico.obter_equipamento(cadastro, eq.id).numero_serie == "450994"


def test_numeros_de_serie_diferentes_no_mesmo_envio_nao_registram(cadastro):
    eq = servico.criar_equipamento(cadastro, "estacao", "Estação mista")
    pasta = PASTA_DADOS / "2026100804"
    resumo = servico.importar_arquivos(cadastro, eq.id, [
        ("20261008041600.txt", (pasta / "20261008041600.txt").read_bytes() + b"serie:111111\n"),
        ("20261008041800.txt", (pasta / "20261008041800.txt").read_bytes() + b"serie:222222\n"),
    ])
    assert any("nenhum foi registrado" in a for a in resumo.avisos)
    assert servico.obter_equipamento(cadastro, eq.id).numero_serie is None


def test_consultas_por_periodo(cadastro, equipamento, pasta_sd):
    servico.importar_caminho(cadastro, equipamento.id, pasta_sd)
    todas = consultas.buscar_leituras(cadastro, equipamento.id)
    assert len(todas) == N_ARQUIVOS - 1 and [l["tempo"] for l in todas] == sorted(l["tempo"] for l in todas)
    assert todas[0]["arquivo"] == "20261008040800.txt" and todas[-1]["chuva"] == 42.1
    so_outubro_8 = consultas.buscar_leituras(cadastro, equipamento.id, datetime(2026, 10, 8), datetime(2026, 10, 8, 23))
    assert len(so_outubro_8) == 7
    assert len(consultas.buscar_leituras(cadastro, equipamento.id, limite=2)) == 2


def test_paralelo_da_o_mesmo_resultado(cadastro, equipamento, pasta_sd, monkeypatch, banco):
    """As unidades lidas nos processos do pool (o plugin importado pelo nome do
    modulo do manifesto) dao as mesmas linhas que a leitura neste processo."""
    from app.nucleo import paralelo
    original = paralelo.mapear_lotes
    monkeypatch.setattr(paralelo, "processos", 2)
    monkeypatch.setattr(paralelo, "mapear_lotes",
                        lambda f, itens, **kw: original(f, itens, tamanho_lote=4, minimo_paralelo=1))
    try:
        resumo = servico.importar_caminho(cadastro, equipamento.id, pasta_sd)
    finally:
        paralelo.encerrar()
    assert (resumo.leituras, resumo.novas, resumo.corrompidas) == (N_ARQUIVOS, N_ARQUIVOS, 1)
    with banco.sessao() as sessao:
        arquivos = sorted(sessao.scalars(select(EstacaoLeitura.arquivo)))
    assert arquivos == sorted(p.name for p in PASTA_DADOS.rglob("*.txt"))


# ------------------------------------------------------------------ protecoes

def _zip_com(nomes_conteudos) -> bytes:
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w", zipfile.ZIP_DEFLATED) as z:
        for nome, conteudo in nomes_conteudos:
            z.writestr(nome, conteudo)
    return saida.getvalue()


@pytest.mark.parametrize("nome", ["../20261008041600.txt", "a/../../20261008041600.txt",
                                  "/etc/20261008041600.txt", "C:\\x\\20261008041600.txt",
                                  "..\\..\\20261008041600.txt"])
def test_path_traversal_no_zip_e_rejeitado(cadastro, equipamento, nome):
    with pytest.raises(ErroEnvio, match="nao permitido"):
        servico.importar_arquivos(cadastro, equipamento.id, [("SD.zip", _zip_com([(nome, "x")]))])
    assert servico.listar_envios(cadastro) == []


def test_path_traversal_no_nome_do_upload_e_rejeitado(cadastro, equipamento):
    with pytest.raises(ErroEnvio):
        servico.importar_arquivos(cadastro, equipamento.id, [("../../20261008041600.txt", b"x")])


def test_zip_bomb_limite_total(cadastro, equipamento, banco):
    servico.iniciar(url=banco.url, config=config_teste(banco.url, max_descompactado=50_000))
    conteudo = (PASTA_DADOS / "2026100804" / "20261008041600.txt").read_bytes() + b"#" * 5000  # ~5 kB
    arquivos = [(f"20261008{h:02d}0000.txt", conteudo) for h in range(20)]
    with pytest.raises(LimiteExcedido):
        servico.importar_arquivos(cadastro, equipamento.id, [("SD.zip", _zip_com(arquivos))])


def test_zip_bomb_arquivo_grande(cadastro, equipamento):
    bomba = _zip_com([("20261008041600.txt", b"0" * (5 * 1024 * 1024))])
    assert len(bomba) < 20_000
    with pytest.raises(LimiteExcedido):
        servico.importar_arquivos(cadastro, equipamento.id, [("SD.zip", bomba)])


def test_zip_bomb_em_arquivo_ignorado_nem_e_lido(cadastro, equipamento):
    arq = (PASTA_DADOS / "2026102116" / "20261021160000.txt").read_bytes()
    bomba = _zip_com([("lixo.bin", b"0" * (5 * 1024 * 1024)), ("20261021160000.txt", arq)])
    resumo = servico.importar_arquivos(cadastro, equipamento.id, [("SD.zip", bomba)])
    assert (resumo.ignorados, resumo.novas) == (1, 1)


def test_zip_invalido(cadastro, equipamento):
    with pytest.raises(ErroEnvio, match="ZIP invalido"):
        servico.importar_arquivos(cadastro, equipamento.id, [("SD.zip", b"PK\x03\x04lixo")])


# ------------------------------------------------------------------ RAR

def _arquivos_rar():
    arquivos = {f"{p.parent.name}/{p.name}": p.read_bytes() for p in sorted(PASTA_DADOS.rglob("*.txt"))}
    arquivos["estacao_erros.log"] = b"x"
    return arquivos


def test_rar_armazenado(cadastro, equipamento, tmp_path):
    caminho = tmp_path / "SD.rar"
    caminho.write_bytes(criar_rar(_arquivos_rar()))
    resumo = servico.importar_caminho(cadastro, equipamento.id, caminho)
    assert resumo.tipo == "rar"
    assert (resumo.leituras, resumo.novas, resumo.corrompidas, resumo.ignorados) == (N_ARQUIVOS, N_ARQUIVOS, 1, 1)
    # tambem como upload
    resumo = servico.importar_arquivos(cadastro, equipamento.id, [("SD.rar", caminho.read_bytes())])
    assert resumo.duplicadas == N_ARQUIVOS


def test_rar_comprimido_sem_programa_da_erro_claro(cadastro, equipamento, tmp_path, monkeypatch):
    monkeypatch.setattr(extracao, "suporte_rar",
                        lambda: (None, "nenhum programa para descompactar RAR. " + extracao.INSTRUCAO_RAR))
    caminho = tmp_path / "SD.rar"
    caminho.write_bytes(criar_rar(_arquivos_rar(), metodo=0x33))
    with pytest.raises(ErroRarSemFerramenta, match="unrar"):
        servico.importar_caminho(cadastro, equipamento.id, caminho)


def test_rar_comprimido_de_verdade(cadastro, equipamento, tmp_path, pasta_sd):
    import shutil
    import subprocess
    if not shutil.which("rar"):
        pytest.skip("sem o programa rar para gerar um .rar comprimido")
    if extracao.suporte_rar()[0] is None:
        pytest.skip("sem unrar/unar/bsdtar para descompactar")
    caminho = tmp_path / "SD.rar"
    subprocess.run(["rar", "a", "-r", "-ep1", str(caminho), str(pasta_sd) + "/"], check=True, capture_output=True)
    _confere_sd(servico.importar_caminho(cadastro, equipamento.id, caminho), "local", "rar")
