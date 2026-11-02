"""Consultas da estação (perfil leitura), usadas pelas abas, pela API e pelos testes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlalchemy import func, select

from hidrolog_nucleo.plugin import obter_equipamento_orm, sessao_autorizada

from .dados import EstacaoLeitura as L

COLUNAS = ("tempo", "arquivo", "corrompido", "chuva", "temperatura", "status", "tensao", "numero_serie",
           "firmware")


@dataclass(frozen=True)
class ResumoLeituras:
    leituras: int
    corrompidas: int
    inicio: Optional[datetime]
    fim: Optional[datetime]


def _filtro(consulta, equipamento_id, inicio, fim):
    consulta = consulta.where(L.equipamento_id == equipamento_id)
    if inicio is not None:
        consulta = consulta.where(L.tempo >= inicio)
    if fim is not None:
        consulta = consulta.where(L.tempo <= fim)
    return consulta


def resumo_leituras(usuario, equipamento_id: int, inicio=None, fim=None) -> ResumoLeituras:
    with sessao_autorizada(usuario, "leitura") as (sessao, _):
        obter_equipamento_orm(sessao, equipamento_id, "estacao")
        n, corrompidas, a, b = sessao.execute(_filtro(
            select(func.count(L.id), func.coalesce(func.sum(L.corrompido), 0), func.min(L.tempo), func.max(L.tempo)),
            equipamento_id, inicio, fim)).one()
        return ResumoLeituras(n, int(corrompidas), a, b)


def buscar_leituras(usuario, equipamento_id: int, inicio=None, fim=None, limite: int = 100_000,
                    incluir_corrompidas: bool = False) -> list[dict]:
    """Leituras em ordem de tempo, como dicts (sem as corrompidas, por padrão)."""
    with sessao_autorizada(usuario, "leitura") as (sessao, _):
        obter_equipamento_orm(sessao, equipamento_id, "estacao")
        consulta = _filtro(select(L), equipamento_id, inicio, fim)
        if not incluir_corrompidas:
            consulta = consulta.where(L.corrompido.is_(False))
        return [{c: getattr(l, c) for c in COLUNAS}
                for l in sessao.scalars(consulta.order_by(L.tempo).limit(limite))]
