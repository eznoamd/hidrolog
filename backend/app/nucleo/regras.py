"""Motor das regras de qualidade (Plugin.regras), nos tres niveis:

- leitura:      na importacao, a cada lote de leituras novas (ingestao.ao_inserir);
- envio:        ao fim de cada importacao, com o periodo do envio;
- equipamento:  ao abrir o app e depois de cada envio; a ocorrencia fica
                aberta enquanto a condicao vale e e resolvida sozinha depois.

Regras NUNCA alteram dados: as regras-funcao rodam dentro de um savepoint
que e desfeito no fim (mesmo que uma tente gravar algo), e so depois o
nucleo grava as ocorrencias. Uma regra com defeito vai para o log e nao
derruba a importacao.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Iterable, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from hidrolog_nucleo.plugin import ContextoRegra, Ocorrencia, Plugin, Regra

from .modelos import Ocorrencia as OcorrenciaOrm
from .modelos import RegraConfig

log = logging.getLogger("hidrolog.regras")


def configuracoes(sessao: Session, equipamento_id: int) -> dict[str, RegraConfig]:
    return {c.codigo_regra: c for c in sessao.scalars(
        select(RegraConfig).where(RegraConfig.equipamento_id == equipamento_id))}


def efetivos(regra: Regra, config: Optional[RegraConfig]) -> tuple[dict, bool]:
    """(parametros, ativa) da regra para o equipamento: padrao + ajustes."""
    parametros = dict(regra.parametros)
    if config is not None and config.parametros:
        parametros.update({k: v for k, v in config.parametros.items() if k in regra.parametros})
    return parametros, (config.ativa if config is not None else True)


def _avaliar(sessao: Session, regra: Regra, contexto: ContextoRegra, coluna_tempo: str) -> list[Ocorrencia]:
    """Roda a regra num savepoint desfeito no fim: nada que ela faca no banco fica."""
    try:
        aninhada = sessao.begin_nested()
        try:
            return list(regra.avaliar(contexto, coluna_tempo))
        finally:
            aninhada.rollback()
    except Exception:  # noqa: BLE001 - uma regra com defeito nao derruba a importacao
        log.exception("regra %s falhou", regra.codigo)
        return []


def _gravar(sessao: Session, regra: Regra, equipamento_id: int, ocorrencias: Iterable[Ocorrencia],
            envio_id: Optional[int] = None) -> int:
    agora = datetime.now()
    linhas = [OcorrenciaOrm(equipamento_id=equipamento_id, envio_id=envio_id, tempo=o.tempo,
                            codigo_regra=regra.codigo, nivel=regra.nivel,
                            severidade=o.severidade or regra.severidade, mensagem=o.mensagem[:500],
                            criada_em=agora) for o in ocorrencias]
    sessao.add_all(linhas)
    return len(linhas)


def _regras(plugin: Plugin, nivel: str, sessao: Session, equipamento_id: int):
    config = configuracoes(sessao, equipamento_id)
    for regra in plugin.regras:
        if regra.nivel != nivel:
            continue
        parametros, ativa = efetivos(regra, config.get(regra.codigo))
        if ativa:
            yield regra, parametros


def rodar_leitura(sessao: Session, plugin: Plugin, equipamento, envio_id: int, linhas: list[dict]) -> int:
    """Regras de leitura sobre um lote de leituras novas. Devolve quantas ocorrencias."""
    n = 0
    coluna_tempo = plugin.ingestao.coluna_tempo
    for regra, parametros in _regras(plugin, "leitura", sessao, equipamento.id):
        contexto = ContextoRegra(equipamento=equipamento, parametros=parametros, sessao=sessao, linhas=linhas)
        n += _gravar(sessao, regra, equipamento.id, _avaliar(sessao, regra, contexto, coluna_tempo), envio_id)
    return n


def rodar_envio(sessao: Session, plugin: Plugin, equipamento, envio, inicio, fim) -> int:
    n = 0
    for regra, parametros in _regras(plugin, "envio", sessao, equipamento.id):
        contexto = ContextoRegra(equipamento=equipamento, parametros=parametros, sessao=sessao, envio=envio,
                                 inicio=inicio, fim=fim, agora=datetime.now())
        n += _gravar(sessao, regra, equipamento.id, _avaliar(sessao, regra, contexto, "tempo"), envio.id)
    return n


def rodar_equipamento(sessao: Session, plugin: Plugin, equipamento, agora: Optional[datetime] = None) -> int:
    """Regras de equipamento: uma ocorrencia aberta por regra enquanto a
    condicao vale (atualizada a cada rodada) e resolvida sozinha depois.
    Devolve quantas ocorrencias ficaram abertas."""
    agora = agora or datetime.now()
    abertas = 0
    ativas = {r.codigo: p for r, p in _regras(plugin, "equipamento", sessao, equipamento.id)}
    for regra in plugin.regras:
        if regra.nivel != "equipamento":
            continue
        atual = sessao.scalar(select(OcorrenciaOrm).where(
            OcorrenciaOrm.equipamento_id == equipamento.id, OcorrenciaOrm.codigo_regra == regra.codigo,
            OcorrenciaOrm.nivel == "equipamento", OcorrenciaOrm.resolvida_em.is_(None)))
        achadas = []
        if regra.codigo in ativas:
            contexto = ContextoRegra(equipamento=equipamento, parametros=ativas[regra.codigo], sessao=sessao,
                                     agora=agora)
            achadas = _avaliar(sessao, regra, contexto, "tempo")
        if achadas:
            o = achadas[0]
            if atual is None:
                _gravar(sessao, regra, equipamento.id, [o])
            else:
                atual.mensagem = o.mensagem[:500]
                atual.tempo = o.tempo
                atual.severidade = o.severidade or regra.severidade
            abertas += 1
        elif atual is not None:
            atual.resolvida_em = agora           # a condicao deixou de valer (resolvida_por fica nulo)
    return abertas
