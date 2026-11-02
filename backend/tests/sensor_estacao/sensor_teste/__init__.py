"""Sensor de teste do núcleo: uma "estação" fictícia com tudo o que um plugin
pode ter (tabela e migração, ingestão com leitura paralela, nº de série lido,
ficha com migração de atributos, regras nos três níveis, consultas, dois
formatos de exportação, rotas da API, uma aba e a amostra do kit).

Formato: um arquivo AAAAMMDDHHMMSS.txt por leitura (em pastas AAAAMMDDHH ou
soltos), com linhas "chave:valor":

    chuva:1.250          mm/h (obrigatória: sem ela a leitura é corrompida)
    temperatura:21.4     °C
    status:0             0 = normal
    tensao:12.1          V
    serie:450123         nº de série (opcional)
    firmware:2.11.6      (opcional)
    intervalo:60         s entre leituras (opcional)

Não é distribuído: os testes do backend e do front o registram (conftest).
"""

from pathlib import Path

from hidrolog_nucleo.plugin import Exportacao, Ingestao, Plugin, carregar_manifesto

from . import dados, exportacao
from .ficha import FICHA, VERSAO_FICHA, migrar_atributos
from .regras import REGRAS

_PASTA = Path(__file__).parent


def _rotas():
    from .rotas import rotas
    return rotas


PLUGIN = Plugin(
    manifesto=carregar_manifesto(__file__),
    modelos=(dados.EstacaoLeitura,),
    migracoes=_PASTA / "migracoes",
    ingestao=Ingestao(
        tabela=dados.EstacaoLeitura,
        reconhecer=dados.reconhecer,
        ler=dados.ler,
        chave=("equipamento_id", "tempo"),
        coluna_tempo="tempo",
        coluna_corrompido="corrompido",
        coluna_numero_serie="numero_serie",
        leitura_paralela=True,
    ),
    ficha=FICHA,
    versao_ficha=VERSAO_FICHA,
    migrar_atributos=migrar_atributos,
    regras=REGRAS,
    consultas="sensor_teste.consultas",
    exportacao=Exportacao(formatos=exportacao.FORMATOS, exportar=exportacao.exportar),
    interface="sensor_teste.interface",
    rotas=_rotas,
    amostra=_PASTA / "amostra",
)
