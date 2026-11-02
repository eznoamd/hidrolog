import shutil
import sys
import zipfile
from pathlib import Path

import pytest
from argon2 import PasswordHasher

from app import servico
from app.config import Configuracao
from app.nucleo import plugins, seguranca
from app.nucleo.administracao import criar_master

# 13 leituras do sensor de teste (sensor_teste) em 4 pastas de medicao;
# 20261011051200.txt nao tem a chuva (corrompida)
PASTA_DADOS = Path(__file__).resolve().parent / "dados"
N_ARQUIVOS = 13
SENHA = "senha-de-teste"

# o sensor de teste (pacote "sensor_teste", em sensor_estacao/) e os plugins falsos
# entram pelo registro, como plugins de fora do pacote; o app nao traz nenhum
sys.path.insert(0, str(Path(__file__).resolve().parent / "sensor_estacao"))
from sensor_teste import PLUGIN as PLUGIN_ESTACAO  # noqa: E402
from tests.plugin_falso import PLUGIN as PLUGIN_FALSO  # noqa: E402
from tests.plugins_teste.calibrado import PLUGIN as PLUGIN_CALIBRADO  # noqa: E402
from tests.plugins_teste.csvlongo import PLUGIN as PLUGIN_CSV  # noqa: E402

for _plugin in (PLUGIN_ESTACAO, PLUGIN_FALSO, PLUGIN_CSV, PLUGIN_CALIBRADO):
    plugins.registrar(_plugin)

# argon2 barato nos testes (o padrao leva ~0,1 s por hash de proposito)
seguranca._hasher = PasswordHasher(time_cost=1, memory_cost=64, parallelism=1)


def config_teste(url: str, **mudancas) -> Configuracao:
    valores = dict(database_url=url, max_descompactado=64 * 1024 * 1024, max_arquivo_leitura=1024 * 1024,
                   max_arquivos=100_000, processos=1)
    valores.update(mudancas)
    return Configuracao(**valores)


@pytest.fixture
def banco(tmp_path):
    url = f"sqlite:///{tmp_path / 'teste.db'}"
    b = servico.iniciar(config=config_teste(url))
    yield b
    servico.encerrar()


@pytest.fixture
def master(banco):
    criar_master(banco, "admin", "Administrador", SENHA)
    return servico.autenticar("admin", SENHA)


@pytest.fixture
def cadastro(master):
    servico.criar_usuario(master, "cad", "Cadastro", SENHA, "cadastro")
    return servico.autenticar("cad", SENHA)


@pytest.fixture
def leitor(master):
    servico.criar_usuario(master, "ler", "Leitura", SENHA, "leitura")
    return servico.autenticar("ler", SENHA)


@pytest.fixture
def equipamento(cadastro):
    return servico.criar_equipamento(cadastro, "estacao", "Estação teste", numero_serie="450123")


@pytest.fixture
def pasta_sd(tmp_path):
    """Copia do SD: as leituras + os arquivos que nao sao leituras."""
    destino = tmp_path / "SD"
    shutil.copytree(PASTA_DADOS, destino)
    (destino / "estacao_erros.log").write_text("20261011051200 sem a chuva\n")
    log = destino / "Logger" / "Backup"
    log.mkdir(parents=True)
    (log / "logger_backup.csv").write_text("data;evento\n")
    return destino


@pytest.fixture
def zip_sd(tmp_path, pasta_sd):
    """ZIP do SD com nomes no estilo do Windows (separador "\\")."""
    caminho = tmp_path / "SD.zip"
    with zipfile.ZipFile(caminho, "w", zipfile.ZIP_DEFLATED) as z:
        for arq in sorted(pasta_sd.rglob("*")):
            if arq.is_file():
                z.write(arq, str(arq.relative_to(pasta_sd)).replace("/", "\\"))
    return caminho
