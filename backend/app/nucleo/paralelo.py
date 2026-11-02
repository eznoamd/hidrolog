"""Pool de processos reaproveitado, para plugins que interpretam muitos
arquivos (ex.: um cartao SD com ~11 mil .txt leva ~17 s num processo so).

Usa "spawn" (igual em Linux, Windows e macOS). Num app congelado
(PyInstaller etc.) chame multiprocessing.freeze_support() no inicio, ou use
HIDROLOG_PROCESSOS=1. Se o pool falhar, cai para um processo so."""

from __future__ import annotations

import contextvars
import multiprocessing
import os
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from contextlib import contextmanager
from typing import Callable, Iterator, Optional, Sequence, TypeVar

T = TypeVar("T")
R = TypeVar("R")

_pool: Optional[ProcessPoolExecutor] = None
_pool_processos = 0
processos = int(os.environ.get("HIDROLOG_PROCESSOS", str(min(4, os.cpu_count() or 1))))

# progresso opcional de mapear_lotes: funcao(feitos, total), definida por
# quem chama o plugin (app.servico.importar_arquivos) com informar_progresso()
_progresso: contextvars.ContextVar[Optional[Callable[[int, int], None]]] = \
    contextvars.ContextVar("hidrolog_progresso_lotes", default=None)


@contextmanager
def informar_progresso(funcao: Optional[Callable[[int, int], None]]) -> Iterator[None]:
    """Durante o bloco, mapear_lotes chama funcao(feitos, total) a cada lote
    pronto (na thread de quem chamou). Se a funcao levantar uma excecao, o
    mapeamento para e a excecao sobe (serve para cancelar)."""
    marca = _progresso.set(funcao)
    try:
        yield
    finally:
        _progresso.reset(marca)


def progresso_atual() -> Optional[Callable[[int, int], None]]:
    """A funcao de progresso definida por informar_progresso (ou None)."""
    return _progresso.get()


def configurar(n: int) -> None:
    global processos
    processos = max(1, int(n))


def _obter_pool() -> ProcessPoolExecutor:
    global _pool, _pool_processos
    if _pool is None or _pool_processos != processos:
        encerrar()
        _pool = ProcessPoolExecutor(max_workers=processos, mp_context=multiprocessing.get_context("spawn"))
        _pool_processos = processos
    return _pool


def encerrar() -> None:
    global _pool
    if _pool is not None:
        _pool.shutdown(cancel_futures=True)
        _pool = None


def mapear_lotes(funcao: Callable[[list[T]], list[R]], itens: Sequence[T],
                 tamanho_lote: int = 500, minimo_paralelo: int = 1000) -> list[R]:
    """funcao(lote) -> lista, aplicada em lotes; resultado na ordem dos itens.
    `funcao` precisa ser uma funcao de modulo (importavel pelos processos)."""
    itens = list(itens)
    avisar = _progresso.get()
    if processos <= 1 or len(itens) < minimo_paralelo:
        if avisar is None:
            return funcao(itens)
        return _em_sequencia(funcao, itens, tamanho_lote, avisar)
    lotes = [itens[i:i + tamanho_lote] for i in range(0, len(itens), tamanho_lote)]
    try:
        saida: list = []
        for resultado in _obter_pool().map(funcao, lotes):
            saida.extend(resultado)
            if avisar is not None:
                avisar(len(saida), len(itens))
        return saida
    except (BrokenProcessPool, OSError, RuntimeError):
        encerrar()
        if avisar is None:
            return funcao(itens)
        return _em_sequencia(funcao, itens, tamanho_lote, avisar)


def _em_sequencia(funcao, itens: list, tamanho_lote: int, avisar: Callable[[int, int], None]) -> list:
    saida: list = []
    for i in range(0, len(itens), tamanho_lote):
        saida.extend(funcao(itens[i:i + tamanho_lote]))
        avisar(len(saida), len(itens))
    return saida
