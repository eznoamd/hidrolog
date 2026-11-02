"""Plugin de exemplo do Hidrolog: um termometro que grava um CSV com uma
leitura por linha (data_hora;temperatura_c). E o modelo de referencia de
COMO-CRIAR-UM-PLUGIN.md (na pasta do exemplo): tudo o que um plugin tem, no menor tamanho."""

from pathlib import Path

from hidrolog_nucleo.plugin import Exportacao, Ingestao, Plugin, carregar_manifesto

from . import dados
from .ficha import FICHA
from .regras import REGRAS

PLUGIN = Plugin(
    manifesto=carregar_manifesto(__file__),
    modelos=(dados.TermometroLeitura,),
    migracoes=Path(__file__).parent / "migracoes",
    ingestao=Ingestao(tabela=dados.TermometroLeitura, reconhecer=dados.reconhecer, ler=dados.ler,
                      chave=("equipamento_id", "tempo")),
    ficha=FICHA,
    regras=REGRAS,
    consultas="hidrolog_termometro.dados",
    exportacao=Exportacao(formatos=dados.FORMATOS, exportar=dados.exportar),
    interface="hidrolog_termometro.interface",
    amostra=Path(__file__).parent / "amostra",
)
