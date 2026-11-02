"""Plugins de sensor do lado da interface.

O plugin e um pacote so (hidrolog_nucleo.plugin.Plugin), descoberto pelo
backend (app.nucleo.plugins). A interface dele e o modulo `Plugin.interface`,
importado aqui sob demanda, com a lista ABAS (hidrolog_nucleo.plugin.Aba).
Um tipo de sensor sem plugin carregado, ou sem interface, fica so com as
abas comuns do nucleo.

O nucleo da interface nao importa nada de nenhum sensor: so chama
`Aba.fabrica(ContextoAba)`.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from app import servico
from app.nucleo import plugins as plugins_backend
from app.nucleo.tipos import Equipamento
from hidrolog_nucleo.plugin import Aba, ContextoAba, Plugin

from . import tarefas

if TYPE_CHECKING:
    from .contexto import Contexto

log = logging.getLogger("hidrolog.registro")

_abas: dict[str, Optional[list[Aba]]] = {}


def plugin(codigo: str) -> Optional[Plugin]:
    """O plugin carregado do tipo de sensor (None se ausente, desativado ou com falha)."""
    return plugins_backend.talvez(codigo)


def abas(codigo: str) -> Optional[list[Aba]]:
    """As abas que o plugin do tipo oferece, ou None se a interface dele nao
    esta disponivel (sem plugin, sem modulo de interface ou com erro, que vai
    para o log: um plugin com defeito nao derruba o app)."""
    if codigo in _abas:
        return _abas[codigo]
    p = plugin(codigo)
    lista = None
    if p is not None and p.interface:
        try:
            modulo = p.modulo_interface()
            lista = [a for a in getattr(modulo, "ABAS", []) if isinstance(a, Aba)]
        except Exception:  # noqa: BLE001
            log.exception("a interface do plugin %s nao carregou", codigo)
            lista = None
    _abas[codigo] = lista or None
    return _abas[codigo]


def esquecer() -> None:
    """Descarta as abas em cache (testes, troca de plugins)."""
    _abas.clear()


def _executar(funcao, *args, ao_concluir, ao_falhar, nome: str = "tarefa"):
    return tarefas.executar(funcao, *args, ao_concluir=ao_concluir, ao_falhar=ao_falhar, nome=nome)


def contexto_aba(ctx: "Contexto", equipamento: Equipamento, inicio: Optional[datetime] = None,
                 fim: Optional[datetime] = None, ocultar_suspeitas: bool = False) -> ContextoAba:
    """O ContextoAba pronto que cada aba recebe."""
    p = plugin(equipamento.tipo_sensor)
    consultas = None
    if p is not None and p.consultas:
        try:
            consultas = p.modulo_consultas()
        except Exception:  # noqa: BLE001
            log.exception("as consultas do plugin %s nao carregaram", equipamento.tipo_sensor)
    usuario = ctx.usuario

    def suspeitas() -> set:
        funcao = getattr(servico, "tempos_suspeitos", None)
        return funcao(usuario, equipamento.id, inicio, fim) if funcao else set()

    return ContextoAba(equipamento=equipamento, usuario=usuario, inicio=inicio, fim=fim, consultas=consultas,
                       ocultar_suspeitas=ocultar_suspeitas, suspeitas=suspeitas, executar=_executar,
                       tratar_erro=ctx.tratar_erro, sessao=ctx, versao_dados=ctx.versao_dados)
