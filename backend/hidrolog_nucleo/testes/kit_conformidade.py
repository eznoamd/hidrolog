"""Testes genericos que todo plugin do Hidrolog precisa passar (pytest --plugin=<codigo>).

Cada plugin traz uma amostra minima de dados reais (Plugin.amostra) para a
importacao, a reimportacao, as regras, as abas e as exportacoes.
"""

from __future__ import annotations

import csv
import importlib
import logging
import os
import subprocess
import sys
from pathlib import Path

import pytest

from hidrolog_nucleo.plugin import (
    NOME_MANIFESTO, ArquivoMemoria, ArvoreArquivos, ContextoRegra, Plugin, PlanoImportacao, Recusa,
    contrato_compativel, ler_manifesto,
)

SENHA = "senha-do-kit-123"
pytestmark = pytest.mark.conformidade


# ============================================================================ fixtures

def _achar_plugin(codigo: str, pasta_opcao) -> tuple[Plugin, Path | None]:
    """(plugin, pasta do manifesto). Entry point primeiro; senao a pasta."""
    from importlib import metadata

    for ponto in metadata.entry_points(group="hidrolog.plugins"):
        if ponto.name == codigo:
            plugin = ponto.load()
            modulo = sys.modules[plugin.manifesto.modulo.split(".")[0]]
            return plugin, _pasta_manifesto(Path(modulo.__file__).parent)
    candidatas = [Path(pasta_opcao)] if pasta_opcao else [Path.cwd(), *Path.cwd().parents[:1]]
    for pasta in candidatas:
        toml = pasta / NOME_MANIFESTO
        if toml.is_file() and ler_manifesto(toml).codigo == codigo:
            manifesto = ler_manifesto(toml)
            if str(pasta) not in sys.path:
                sys.path.insert(0, str(pasta))
            return importlib.import_module(manifesto.modulo).PLUGIN, pasta
    pytest.exit(f"plugin {codigo!r} nao encontrado (nem por entry point nem em {candidatas})", returncode=4)


def _pasta_manifesto(pasta_pacote: Path) -> Path | None:
    for p in (pasta_pacote, pasta_pacote.parent, pasta_pacote.parent.parent):
        if (p / NOME_MANIFESTO).is_file():
            return p
    return None


@pytest.fixture(scope="session")
def achado(request):
    return _achar_plugin(request.config.getoption("plugin"), request.config.getoption("plugin_pasta"))


@pytest.fixture(scope="session")
def plugin(achado) -> Plugin:
    return achado[0]


@pytest.fixture
def app(plugin, tmp_path, monkeypatch):
    """Banco temporario com o plugin carregado, um master e um equipamento do tipo."""
    from argon2 import PasswordHasher

    from app import servico
    from app.config import Configuracao
    from app.nucleo import plugins, seguranca
    from app.nucleo.administracao import criar_master

    monkeypatch.setattr(seguranca, "_hasher", PasswordHasher(time_cost=1, memory_cost=64, parallelism=1))
    if plugins.talvez(plugin.codigo) is None:
        plugins.registrar(plugin)
    pasta = tmp_path / "dados"
    pasta.mkdir()
    config = Configuracao(database_url=f"sqlite:///{pasta / 'hidrolog.db'}", max_descompactado=512 * 1024 * 1024,
                          max_arquivo_leitura=8 * 1024 * 1024, max_arquivos=200_000, processos=1)
    banco = servico.iniciar(config=config)
    criar_master(banco, "kit", "Kit de conformidade", SENHA)
    usuario = servico.autenticar("kit", SENHA)
    eq = servico.criar_equipamento(usuario, plugin.codigo, "Equipamento do kit")
    yield servico, usuario, eq, banco
    servico.encerrar()


@pytest.fixture
def importado(app, plugin):
    servico, usuario, eq, banco = app
    if plugin.amostra is None or not Path(plugin.amostra).exists():
        pytest.fail("o plugin precisa declarar Plugin.amostra (dados reais minimos) para o kit")
    resumo = servico.importar_caminho(usuario, eq.id, plugin.amostra)
    return app, resumo


# ============================================================================ manifesto e contrato

def test_manifesto_valido(plugin, achado):
    assert isinstance(plugin, Plugin)
    pasta = achado[1]
    assert pasta is not None, f"falta o {NOME_MANIFESTO} ao lado do pacote"
    assert ler_manifesto(pasta) == plugin.manifesto, "o PLUGIN deve usar o manifesto do hidrolog-plugin.toml"
    assert plugin.manifesto.nome and plugin.manifesto.versao


def test_contrato_compativel(plugin):
    assert contrato_compativel(plugin.manifesto.contrato)


def test_backend_nao_importa_qt(plugin):
    """O modulo do plugin (sem a interface) carrega sem PySide6."""
    codigo = (f"import sys; import {plugin.manifesto.modulo}; "
              "assert not any(m.startswith('PySide6') for m in sys.modules), 'importou PySide6'")
    env = dict(os.environ, PYTHONPATH=os.pathsep.join(p for p in sys.path if p))
    r = subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True, env=env, timeout=120)
    assert r.returncode == 0, r.stderr[-2000:]


# ============================================================================ migracoes

def test_migracoes_sobem_e_descem(plugin, tmp_path):
    from alembic import command
    from sqlalchemy import create_engine, inspect

    from app.nucleo import plugins
    from app.nucleo.banco import config_alembic

    if plugins.talvez(plugin.codigo) is None:
        plugins.registrar(plugin)
    assert plugin.migracoes and Path(plugin.migracoes).is_dir(), "o plugin precisa de migracoes (Plugin.migracoes)"
    url = f"sqlite:///{tmp_path / 'migracoes.db'}"
    cfg = config_alembic(url)
    engine = create_engine(url)
    tabela = plugin.ingestao.tabela.__tablename__
    with engine.begin() as conexao:
        cfg.attributes["connection"] = conexao
        command.upgrade(cfg, "nucleo@head")
        command.upgrade(cfg, f"{plugin.codigo}@head")
        assert tabela in inspect(conexao).get_table_names()
        command.downgrade(cfg, f"{plugin.codigo}@base")
        assert tabela not in inspect(conexao).get_table_names()
        command.upgrade(cfg, f"{plugin.codigo}@head")
        assert tabela in inspect(conexao).get_table_names()
    engine.dispose()


# ============================================================================ ingestao

def test_importa_a_amostra(importado, plugin):
    _app, resumo = importado
    assert resumo.leituras > 0, "a amostra nao gerou nenhuma leitura"
    assert resumo.novas == resumo.leituras - resumo.duplicadas
    assert resumo.inicio is not None and resumo.fim is not None


def test_reimportacao_nao_duplica(importado, plugin):
    (servico, usuario, eq, _banco), primeiro = importado
    segundo = servico.importar_caminho(usuario, eq.id, plugin.amostra)
    assert segundo.novas == 0
    assert segundo.duplicadas == primeiro.leituras
    assert servico.resumo_leituras(usuario, eq.id).leituras == primeiro.novas


def test_reconhecer_aceita_a_amostra_na_verificacao(app, plugin):
    servico = app[0]
    tipos = {t.codigo for t in servico.sugerir_tipo([plugin.amostra])}
    assert plugin.codigo in tipos


def test_reconhecer_recusa_arvore_vazia(plugin):
    resultado = plugin.ingestao.reconhecer(ArvoreArquivos([]))
    assert isinstance(resultado, Recusa) and resultado.motivo.strip()


def test_reconhecer_recusa_outro_sensor(plugin):
    outro = ArvoreArquivos([
        ArquivoMemoria("foto.jpg", b"\xff\xd8\xff\xe0" + b"\x00" * 64),
        ArquivoMemoria("outro_sensor/medidas.dat", b"\x01\x02\x03\x04" * 16),
        ArquivoMemoria("leia-me.md", "dados de outro equipamento\n".encode()),
        ArquivoMemoria("planilha.csv", "data;umidade\n2026-01-01 00:00;55\n".encode()),
    ])
    resultado = plugin.ingestao.reconhecer(outro)
    assert isinstance(resultado, Recusa) and resultado.motivo.strip(), \
        f"reconhecer aceitou arquivos de outro sensor: {resultado}"


# ============================================================================ ficha

def _valores_invalidos(campo) -> list:
    if campo.tipo in ("inteiro", "decimal"):
        ruins = ["nao e numero"]
        if campo.maximo is not None:
            ruins.append(campo.maximo + 1)
        if campo.minimo is not None:
            ruins.append(campo.minimo - 1)
        if campo.tipo == "inteiro":
            ruins.append("1,5")
        return ruins
    if campo.tipo == "escolha":
        return ["__fora_das_opcoes__"]
    if campo.tipo == "data":
        return ["31/02/2020x"]
    if campo.tipo == "booleano":
        return ["talvez"]
    return []


def test_ficha_aceita_o_padrao_e_recusa_invalidos(app, plugin):
    from app.nucleo.erros import ErroValidacao

    servico, usuario, eq, _banco = app
    editaveis = [c for c in plugin.ficha if c.editavel]
    assert eq.versao_ficha == plugin.versao_ficha
    for campo in editaveis:
        if campo.padrao is not None:
            assert campo.validar(campo.padrao) is not None
        for ruim in _valores_invalidos(campo):
            with pytest.raises(ErroValidacao) as erro:
                servico.alterar_equipamento(usuario, eq.id, atributos={campo.chave: ruim})
            assert campo.chave in erro.value.campos, (campo.chave, ruim)
    with pytest.raises(ErroValidacao):
        servico.alterar_equipamento(usuario, eq.id, atributos={"campo_que_nao_existe": 1})
    for campo in plugin.ficha:
        if campo.origem == "leituras":
            assert not campo.editavel
            assert campo.coluna is None or hasattr(plugin.ingestao.tabela, campo.coluna), campo.chave


# ============================================================================ regras

def test_regras_em_dados_vazios(app, plugin):
    servico, usuario, eq, banco = app
    from datetime import datetime

    with banco.sessao() as sessao:
        for regra in plugin.regras:
            for contexto in (ContextoRegra(eq, dict(regra.parametros), sessao, linhas=[], agora=datetime.now()),
                             ContextoRegra(eq, dict(regra.parametros), sessao, inicio=datetime(2000, 1, 1),
                                           fim=datetime(2000, 1, 2), agora=datetime.now())):
                saida = regra.avaliar(contexto)
                assert isinstance(saida, list), regra.codigo
                assert saida == [] or regra.nivel == "equipamento", (regra.codigo, saida)


def test_regras_rodam_com_a_amostra(importado, plugin, caplog):
    (servico, usuario, eq, _banco), _resumo = importado
    with caplog.at_level(logging.ERROR, logger="hidrolog.regras"):
        servico.reavaliar_equipamentos(eq.id)
    assert not [r for r in caplog.records if r.name == "hidrolog.regras"], "uma regra falhou com a amostra"
    codigos = {r.codigo for r in plugin.regras}
    assert {o.codigo_regra for o in servico.listar_ocorrencias(usuario, eq.id, abertas=None)} <= codigos
    assert {r.codigo for r in servico.listar_regras(usuario, eq.id)} == codigos


# ============================================================================ exportacao

def test_exportacoes_reabrem(importado, plugin, tmp_path):
    (servico, usuario, eq, _banco), resumo = importado
    for formato in plugin.formatos_exportacao():
        r = servico.exportar(usuario, eq.id, None, None, formato.codigo, tmp_path / f"saida{formato.extensao}")
        caminho = Path(r.caminho)
        assert caminho.exists() and caminho.stat().st_size > 0, formato.codigo
        assert r.leituras == resumo.novas, formato.codigo
        if formato.extensao == ".csv":
            with open(caminho, encoding="utf-8", newline="") as f:
                linhas = list(csv.reader(f))
            assert len(linhas) == r.leituras + 1, "uma linha por leitura + cabecalho"
            assert "qualidade" in linhas[0], "as exportacoes levam a coluna de qualidade"
        elif formato.extensao == ".nc":
            netCDF4 = pytest.importorskip("netCDF4")
            with netCDF4.Dataset(caminho) as nc:
                assert len(nc.dimensions["time"]) == r.leituras
                assert "qualidade" in nc.variables


# ============================================================================ interface

@pytest.fixture(scope="session")
def qapp_kit():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    QtWidgets = pytest.importorskip("PySide6.QtWidgets")
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    try:
        from design.tema import aplicar_tema
        aplicar_tema(app, "claro")
    except ImportError:
        pass
    return app


class _Sessao:
    extras: dict = {}


def _contexto(plugin, servico, usuario, eq):
    from hidrolog_nucleo.plugin import ContextoAba

    consultas = plugin.modulo_consultas()
    return ContextoAba(equipamento=servico.obter_equipamento(usuario, eq.id), usuario=usuario,
                       consultas=consultas, suspeitas=lambda: servico.tempos_suspeitos(usuario, eq.id),
                       executar=None, tratar_erro=lambda e, *_: str(e), sessao=_Sessao())


def test_abas_abrem_sem_e_com_dados(app, plugin, qapp_kit):
    if not plugin.interface:
        pytest.skip("o plugin nao tem interface (so as abas comuns do nucleo)")
    from PySide6.QtWidgets import QWidget

    servico, usuario, eq, _banco = app
    abas = plugin.modulo_interface().ABAS
    assert abas, "o modulo de interface precisa da lista ABAS"
    assert len({a.chave for a in abas}) == len(abas), "chaves de aba repetidas"
    for aba in abas:                                         # sem dados
        w = aba.fabrica(_contexto(plugin, servico, usuario, eq))
        assert isinstance(w, QWidget), aba.chave
        qapp_kit.processEvents()
        w.deleteLater()
    servico.importar_caminho(usuario, eq.id, plugin.amostra)
    _Sessao.extras = {}
    contexto = _contexto(plugin, servico, usuario, eq)
    for aba in abas:                                         # com dados (e atualizar)
        w = aba.fabrica(contexto)
        w.resize(1200, 800)
        w.show()
        qapp_kit.processEvents()
        if hasattr(w, "atualizar"):
            w.atualizar(contexto)
            qapp_kit.processEvents()
        w.close()
        w.deleteLater()
    qapp_kit.processEvents()
