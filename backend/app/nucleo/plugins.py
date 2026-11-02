"""Descoberta e registro dos plugins de sensor (contrato em hidrolog_nucleo.plugin).

Duas fontes, lidas ao abrir o app (servico.iniciar -> carregar):

1. entry points do grupo "hidrolog.plugins" (pacotes instalados com
   `pip install -e`): o caminho do desenvolvimento e dos plugins que vem com o app;
2. a pasta de plugins do app (<dados do app>/plugins/<codigo>/<versao>/), onde o
   gerenciador de plugins instala; a versao ativa de cada um fica em
   <dados do app>/plugins/plugins.json.

Se o mesmo codigo vier das duas, vale o entry point (desenvolvimento) e a
tela Plugins mostra o conflito. Cada plugin e conferido ao carregar
(manifesto, contrato, codigo repetido); um plugin com problema nao e
carregado, os dados dele ficam no banco e o motivo fica em situacoes().
Plugins de fora (ex. nos testes) entram com registrar(plugin).
"""

from __future__ import annotations

import importlib
import json
import logging
import os
import sys
from dataclasses import dataclass, replace
from importlib import metadata
from pathlib import Path
from typing import Optional

from hidrolog_nucleo.plugin import (
    GRUPO_ENTRY_POINTS,
    VERSAO_CONTRATO,
    ErroManifesto,
    Plugin,
    contrato_compativel,
    ler_manifesto,
)

from .erros import NaoEncontrado

log = logging.getLogger("hidrolog.plugins")
NOME_ESTADO = "plugins.json"


@dataclass(frozen=True)
class SituacaoPlugin:
    """Como um plugin ficou na ultima carga (para a tela Plugins).

    estado: "ativo", "desativado", "incompativel", "com falha" ou "conflito";
    origem: "interno" (entry point), "pasta", "zip", "github" ou "registro" (testes)."""

    codigo: str
    nome: str
    versao: str
    contrato: str
    origem: str
    estado: str
    motivo: str = ""
    caminho: str = ""
    url: str = ""
    tag: str = ""


_registro: dict[str, Plugin] = {}
_situacoes: dict[str, SituacaoPlugin] = {}
_conflitos: list[SituacaoPlugin] = []
_caminhos_importacao: dict[str, str] = {}      # codigo -> pasta posta no sys.path
_migracoes_inativas: dict[str, Path] = {}      # plugins desativados: so para o Alembic achar as revisoes
_carregado = False
_diretorio: Optional[Path] = None


# ============================================================================ estado da pasta de plugins

def ler_estado(diretorio: Optional[Path]) -> dict:
    """plugins.json: {"plugins": {codigo: {"versao", "ativo", "origem", "url", "tag", "sha256"}},
    "github_confiaveis": [...]}."""
    if diretorio is None:
        return {"plugins": {}, "github_confiaveis": []}
    arquivo = Path(diretorio) / NOME_ESTADO
    try:
        dados = json.loads(arquivo.read_text(encoding="utf-8"))
    except FileNotFoundError:
        dados = {}
    except (OSError, ValueError) as erro:
        log.error("estado dos plugins ilegivel (%s): %s", arquivo, erro)
        dados = {}
    dados.setdefault("plugins", {})
    dados.setdefault("github_confiaveis", [])
    return dados


def gravar_estado(diretorio: Path, estado: dict) -> None:
    """Grava plugins.json de forma atomica."""
    diretorio = Path(diretorio)
    diretorio.mkdir(parents=True, exist_ok=True)
    temporario = diretorio / f".{NOME_ESTADO}.tmp"
    temporario.write_text(json.dumps(estado, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    os.replace(temporario, diretorio / NOME_ESTADO)


def diretorio() -> Optional[Path]:
    return _diretorio


# ============================================================================ registro

def _situacao(plugin: Plugin, origem: str, estado: str = "ativo", motivo: str = "", **extra) -> SituacaoPlugin:
    m = plugin.manifesto
    return SituacaoPlugin(m.codigo, m.nome, m.versao, m.contrato, origem, estado, motivo, **extra)


def validar(plugin, codigo_esperado: Optional[str] = None) -> Optional[str]:
    """Motivo para nao carregar o plugin, ou None se ele esta de acordo com o contrato."""
    if not isinstance(plugin, Plugin):
        return f"PLUGIN nao e um hidrolog_nucleo.plugin.Plugin (e {type(plugin).__name__})"
    m = plugin.manifesto
    if codigo_esperado and m.codigo != codigo_esperado:
        return f"o manifesto diz codigo {m.codigo!r}, mas o plugin foi registrado como {codigo_esperado!r}"
    if not contrato_compativel(m.contrato):
        return f"contrato {m.contrato} incompativel (o app usa {VERSAO_CONTRATO.split('.')[0]}.x)"
    if plugin.ingestao is None:
        return "o plugin nao declara a ingestao"
    return None


def registrar(plugin: Plugin, origem: str = "registro") -> Plugin:
    """Registra um plugin ja importado (testes, ou plugins de fora das duas fontes)."""
    motivo = validar(plugin)
    if motivo:
        raise ValueError(motivo)
    existente = _registro.get(plugin.codigo)
    if existente is not None and existente is not plugin:
        raise ValueError(f"ja existe um plugin com o codigo {plugin.codigo!r}")
    _registro[plugin.codigo] = plugin
    _situacoes[plugin.codigo] = _situacao(plugin, origem)
    return plugin


def remover(codigo: str) -> None:
    """Tira um plugin do registro (testes)."""
    _registro.pop(codigo, None)
    _situacoes.pop(codigo, None)
    _caminhos_importacao.pop(codigo, None)


_MANTER = object()


def carregar(diretorio_plugins=_MANTER, forcar: bool = False) -> None:
    """Descobre os plugins (entry points + pasta do app). Sem argumento, usa a
    pasta da ultima carga; None = sem pasta de plugins. Plugins registrados a
    mao continuam registrados."""
    global _carregado, _diretorio
    if diretorio_plugins is not _MANTER:
        novo = Path(diretorio_plugins) if diretorio_plugins is not None else None
        if novo != _diretorio:
            if novo is None:
                redefinir()
            _diretorio = novo
            forcar = True
    if _carregado and not forcar:
        return
    # recomeca so o que veio das fontes (os registrados a mao ficam)
    for codigo, situacao in list(_situacoes.items()):
        if situacao.origem != "registro":
            _registro.pop(codigo, None)
            _situacoes.pop(codigo, None)
    _conflitos.clear()
    _migracoes_inativas.clear()
    estado = ler_estado(_diretorio)
    _carregar_entry_points(estado)
    _carregar_pasta(estado)
    _carregado = True


def _carregar_entry_points(estado: dict) -> None:
    try:
        pontos = metadata.entry_points(group=GRUPO_ENTRY_POINTS)
    except Exception:  # noqa: BLE001
        log.exception("nao foi possivel listar os entry points de plugins")
        return
    for ponto in sorted(pontos, key=lambda p: p.name):
        try:
            plugin = ponto.load()
        except Exception as erro:  # noqa: BLE001 - um plugin quebrado nao derruba o app
            log.exception("plugin %s (entry point) nao carregou", ponto.name)
            _situacoes[ponto.name] = SituacaoPlugin(ponto.name, ponto.name, "?", "?", "interno", "com falha",
                                                    f"{type(erro).__name__}: {erro}")
            continue
        motivo = validar(plugin, ponto.name)
        if motivo:
            log.error("plugin %s nao carregado: %s", ponto.name, motivo)
            situacao = (_situacao(plugin, "interno", "incompativel", motivo) if isinstance(plugin, Plugin)
                        else SituacaoPlugin(ponto.name, ponto.name, "?", "?", "interno", "com falha", motivo))
            _situacoes[ponto.name] = situacao
            continue
        if plugin.codigo in _registro:
            _conflitos.append(_situacao(plugin, "interno", "conflito", "codigo repetido; vale o registrado antes"))
            continue
        if estado["plugins"].get(plugin.codigo, {}).get("ativo") is False and \
                not estado["plugins"][plugin.codigo].get("versao"):
            _situacoes[plugin.codigo] = _situacao(plugin, "interno", "desativado", "desativado pelo master")
            if plugin.migracoes:
                _migracoes_inativas[plugin.codigo] = plugin.migracoes
            continue
        _registro[plugin.codigo] = plugin
        _situacoes[plugin.codigo] = _situacao(plugin, "interno", caminho=_pasta_do_modulo(plugin.manifesto.modulo))


def _carregar_pasta(estado: dict) -> None:
    if _diretorio is None:
        return
    for codigo, registro in sorted(estado["plugins"].items()):
        versao = registro.get("versao")
        if not versao:
            continue        # so o estado (ativo/desativado) de um plugin interno
        pasta = _diretorio / codigo / versao
        extra = dict(caminho=str(pasta), url=registro.get("url") or "", tag=registro.get("tag") or "")
        origem = registro.get("origem") or "pasta"
        try:
            manifesto = ler_manifesto(pasta)
        except ErroManifesto as erro:
            _situacoes.setdefault(codigo, SituacaoPlugin(codigo, codigo, versao, "?", origem, "com falha",
                                                         str(erro), **extra))
            continue
        situacao = SituacaoPlugin(manifesto.codigo, manifesto.nome, manifesto.versao, manifesto.contrato,
                                  origem, "ativo", **extra)
        if not registro.get("ativo", True):
            _migracoes_inativas.setdefault(codigo, _pasta_migracoes(pasta, manifesto.modulo))
            _situacoes.setdefault(codigo, replace(situacao, estado="desativado", motivo="desativado pelo master"))
            continue
        if not contrato_compativel(manifesto.contrato):
            _situacoes.setdefault(codigo, replace(
                situacao, estado="incompativel",
                motivo=f"contrato {manifesto.contrato} (o app usa {VERSAO_CONTRATO.split('.')[0]}.x)"))
            continue
        if codigo in _registro:
            # o de desenvolvimento (entry point) ou o registrado a mao vale
            _conflitos.append(replace(situacao, estado="conflito",
                                      motivo="o mesmo codigo veio de um entry point (desenvolvimento), que vale"))
            continue
        try:
            if str(pasta) not in sys.path:
                sys.path.insert(0, str(pasta))
            plugin = importlib.import_module(manifesto.modulo).PLUGIN
        except Exception as erro:  # noqa: BLE001
            log.exception("plugin %s (pasta) nao carregou", codigo)
            _situacoes[codigo] = replace(situacao, estado="com falha", motivo=f"{type(erro).__name__}: {erro}")
            continue
        motivo = validar(plugin, codigo)
        if motivo:
            _situacoes[codigo] = replace(situacao, estado="incompativel", motivo=motivo)
            continue
        _registro[codigo] = plugin
        _situacoes[codigo] = situacao
        _caminhos_importacao[codigo] = str(pasta)


def _pasta_do_modulo(modulo: str) -> str:
    arquivo = getattr(sys.modules.get(modulo.split(".")[0]), "__file__", None)
    return str(Path(arquivo).parent) if arquivo else ""


def _pasta_migracoes(pasta: Path, modulo: str) -> Path:
    """Onde ficam as migracoes de um plugin da pasta sem importa-lo: procura
    um diretorio com arquivos de revisao dentro do pacote."""
    pacote = pasta / modulo.split(".")[0]
    for candidata in sorted(pacote.rglob("migracoes")):
        if candidata.is_dir() and any(candidata.glob("*.py")):
            return candidata
    return pacote / "migracoes"


def redefinir() -> None:
    """Esquece a pasta de plugins e descarrega o que veio dela (testes): tira
    os modulos do sys.modules, as tabelas da Base e a pasta do sys.path."""
    global _carregado, _diretorio
    from .modelos import Base

    for codigo, pasta in list(_caminhos_importacao.items()):
        plugin = _registro.pop(codigo, None)
        _situacoes.pop(codigo, None)
        if plugin is not None:
            for modelo in plugin.modelos:
                tabela = getattr(modelo, "__table__", None)
                if tabela is not None and tabela.name in Base.metadata.tables:
                    Base.metadata.remove(tabela)
            topo = plugin.manifesto.modulo.split(".")[0]
            for nome in [m for m in sys.modules if m == topo or m.startswith(topo + ".")]:
                del sys.modules[nome]
        if pasta in sys.path:
            sys.path.remove(pasta)
    _caminhos_importacao.clear()
    _diretorio = None
    _carregado = False


# ============================================================================ consultas

def obter(codigo: str) -> Plugin:
    carregar()
    try:
        return _registro[codigo]
    except KeyError:
        situacao = _situacoes.get(codigo)
        if situacao is not None:
            raise NaoEncontrado(f"o plugin do tipo de sensor {codigo!r} nao esta carregado "
                                f"({situacao.estado}: {situacao.motivo})") from None
        raise NaoEncontrado(f"tipo de sensor desconhecido: {codigo!r}") from None


def talvez(codigo: str) -> Optional[Plugin]:
    carregar()
    return _registro.get(codigo)


def todos() -> list[Plugin]:
    carregar()
    return sorted(_registro.values(), key=lambda p: p.codigo)


def situacoes() -> list[SituacaoPlugin]:
    """Todos os plugins vistos na ultima carga (ativos e nao) e os conflitos."""
    carregar()
    return sorted(_situacoes.values(), key=lambda s: s.codigo) + list(_conflitos)


def caminho_importacao(codigo: str) -> Optional[str]:
    """Pasta posta no sys.path para importar o plugin (plugins da pasta do app)."""
    return _caminhos_importacao.get(codigo)


def migracoes_inativas() -> list[Path]:
    """Migracoes de plugins desativados: o Alembic precisa achar as revisoes
    que ja estao no banco, mas elas nao sobem enquanto o plugin estiver desativado."""
    carregar()
    return [p for p in _migracoes_inativas.values() if p and p.is_dir()]
