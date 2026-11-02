"""Kit de conformidade dos plugins: plugin do pytest (entry point pytest11).

    cd plugins/<codigo>
    ../../frontend/venv/bin/python -m pytest --plugin=<codigo>

Roda os testes genericos de kit_conformidade.py contra o plugin: manifesto,
contrato, migracoes que sobem e descem, importacao da amostra, reimportacao
sem duplicar, ficha (aceita e recusa), regras em dados vazios e com dados,
abas (offscreen, sem e com dados), exportacoes que reabrem e o reconhecer
recusando uma arvore vazia e uma de outro sensor.

O plugin e procurado nos entry points "hidrolog.plugins" e, se nao estiver
instalado, na pasta atual (ou em --plugin-pasta): a que tem o
hidrolog-plugin.toml com esse codigo.
"""

from __future__ import annotations

from pathlib import Path

KIT = Path(__file__).with_name("kit_conformidade.py")


def pytest_addoption(parser):
    grupo = parser.getgroup("hidrolog", "kit de conformidade dos plugins do Hidrolog")
    grupo.addoption("--plugin", action="store", default=None, metavar="CODIGO",
                    help="codigo do plugin do Hidrolog a passar pelo kit de conformidade")
    grupo.addoption("--plugin-pasta", action="store", default=None, metavar="PASTA",
                    help="pasta do plugin (com o hidrolog-plugin.toml), se ele nao estiver instalado")


def pytest_configure(config):
    if not config.getoption("plugin"):
        return
    config.addinivalue_line("markers", "conformidade: teste do kit de conformidade dos plugins")
    explicitos = getattr(config, "args_source", None) == getattr(config.ArgsSource, "ARGS", object())
    if explicitos:
        config.args.append(str(KIT))
    else:
        config.args[:] = [str(KIT)]
