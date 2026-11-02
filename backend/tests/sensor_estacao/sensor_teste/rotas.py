"""Rotas da API da estação (casca fina sobre as consultas)."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query

from hidrolog_nucleo.plugin import usuario_da_api

from . import consultas

usuario_atual = usuario_da_api()

rotas = APIRouter(prefix="/estacao", tags=["estacao"])


@rotas.get("/equipamentos/{equipamento_id}/resumo")
def resumo(equipamento_id: int, inicio: Optional[datetime] = None, fim: Optional[datetime] = None,
           usuario=Depends(usuario_atual)):
    return consultas.resumo_leituras(usuario, equipamento_id, inicio, fim)


@rotas.get("/equipamentos/{equipamento_id}/leituras")
def leituras(equipamento_id: int, inicio: Optional[datetime] = None, fim: Optional[datetime] = None,
             limite: int = Query(1000, ge=1, le=20000), usuario=Depends(usuario_atual)):
    return consultas.buscar_leituras(usuario, equipamento_id, inicio, fim, limite)
