"""Trabalho pesado fora da thread da interface.

    tarefa = executar(servico.importar_caminho, usuario, eq_id, caminho,
                      ao_concluir=self._pronto, ao_falhar=self._falhou,
                      ao_progresso=self._progresso)      # injeta ao_progresso=... na função
    tarefa.cancelar()   # a próxima chamada de progresso levanta TarefaCancelada

Como funciona (e por quê):

- A função roda numa thread comum do Python (pool de `concurrent.futures`),
  com a pilha padrão do sistema. As threads do pool do Qt têm pilha pequena,
  e recursões fundas (ex. o SQLAlchemy compilando uma consulta) derrubavam o
  processo de vez em quando.
- A thread de trabalho **nunca toca num objeto do Qt**: ela só conhece o
  número da tarefa e envia resultado, erro e progresso pelo `_Despachante`,
  um único QObject criado na thread da interface que vive o app inteiro. Os
  sinais chegam na thread da interface (conexão enfileirada), onde a `Tarefa`
  (também só da interface) chama os callbacks. Antes, a thread de trabalho
  segurava a `Tarefa`; quando ela soltava a última referência, o QObject era
  destruído na thread errada e o app caía.
- O coletor de lixo do Python roda no meio de qualquer alocação, em qualquer
  thread. Rodando na thread da interface enquanto uma de trabalho estava no
  SQLAlchemy/SQLite, corrompia a memória de vez em quando (o app abortava).
  Por isso `instalar_coleta_de_lixo` desliga a coleta automática e a faz num
  timer da interface, só quando nenhuma tarefa está rodando. A contagem de
  referências continua liberando quase tudo na hora; o timer só limpa ciclos.
"""

from __future__ import annotations

import gc
import itertools
import logging
import threading
from concurrent.futures import Future, ThreadPoolExecutor, wait
from typing import Any, Callable, Optional

from PySide6.QtCore import QCoreApplication, QObject, Qt, QTimer, Signal, Slot

from .erros import TarefaCancelada, registrar

log = logging.getLogger("hidrolog.tarefas")

MAX_THREADS = 4
INTERVALO_COLETA_MS = 1000

_ativas: dict[int, "Tarefa"] = {}
_futuros: dict[int, Future] = {}
_numeros = itertools.count(1)
_executor: Optional[ThreadPoolExecutor] = None
_despachante: Optional["_Despachante"] = None


class _Despachante(QObject):
    """Leva os eventos das threads de trabalho para a thread da interface.
    Um só, criado na thread da interface na primeira tarefa e nunca destruído."""

    concluida = Signal(int, object)
    falhou = Signal(int, object)
    progresso = Signal(int, object)

    def __init__(self):
        super().__init__()
        tipo = Qt.ConnectionType.QueuedConnection
        self.concluida.connect(self._concluida, tipo)
        self.falhou.connect(self._falhou, tipo)
        self.progresso.connect(self._progresso, tipo)

    @Slot(int, object)
    def _concluida(self, numero: int, resultado) -> None:
        tarefa = _ativas.pop(numero, None)
        if tarefa is not None:
            tarefa._concluida(resultado)

    @Slot(int, object)
    def _falhou(self, numero: int, erro) -> None:
        tarefa = _ativas.pop(numero, None)
        if tarefa is not None:
            tarefa._falhou(erro)

    @Slot(int, object)
    def _progresso(self, numero: int, args) -> None:
        tarefa = _ativas.get(numero)
        if tarefa is not None:
            tarefa._progresso(args)


class Tarefa:
    """Uma tarefa em andamento, vista da thread da interface."""

    def __init__(self, numero: int, nome: str, ao_concluir, ao_falhar, ao_progresso):
        self.numero = numero
        self.nome = nome
        self._ao_concluir = ao_concluir
        self._ao_falhar = ao_falhar
        self._ao_progresso = ao_progresso
        self._cancelada = threading.Event()
        self.terminada = False

    def cancelar(self) -> None:
        self._cancelada.set()

    @property
    def cancelada(self) -> bool:
        return self._cancelada.is_set()

    def _chamar(self, funcao, *args) -> None:
        if funcao is None:
            return
        try:
            funcao(*args)
        except RuntimeError as erro:  # widget de destino já destruído (ex.: saiu do app)
            if "already deleted" in str(erro) or "C++ object" in str(erro):
                log.debug("callback de %s ignorado: %s", self.nome, erro)
            else:
                registrar(erro, f"callback de {self.nome}")
        except Exception as erro:  # noqa: BLE001
            registrar(erro, f"callback de {self.nome}")

    def _concluida(self, resultado) -> None:
        self.terminada = True
        self._chamar(self._ao_concluir, resultado)

    def _falhou(self, erro) -> None:
        self.terminada = True
        registrar(erro, self.nome)
        self._chamar(self._ao_falhar, erro)

    def _progresso(self, args) -> None:
        if not self.terminada:
            self._chamar(self._ao_progresso, *args)


def _rodar(numero: int, cancelada: threading.Event, despachante: "_Despachante",
           funcao, args, kwargs) -> None:
    """Corpo da thread de trabalho: só objetos Python comuns e o despachante."""
    try:
        resultado = funcao(*args, **kwargs)
    except BaseException as erro:  # noqa: BLE001 - tudo vira mensagem na interface
        despachante.falhou.emit(numero, erro)
    else:
        despachante.concluida.emit(numero, resultado)


def _iniciar() -> tuple[ThreadPoolExecutor, "_Despachante"]:
    global _executor, _despachante
    if _despachante is None:
        app = QCoreApplication.instance()
        if app is not None and threading.current_thread() is not threading.main_thread():
            raise RuntimeError("tarefas.executar deve ser chamado da thread da interface")
        _despachante = _Despachante()
    if _executor is None:
        _executor = ThreadPoolExecutor(max_workers=MAX_THREADS, thread_name_prefix="hidrolog-tarefa")
    return _executor, _despachante


def executar(funcao: Callable[..., Any], *args, ao_concluir: Optional[Callable] = None,
             ao_falhar: Optional[Callable] = None, ao_progresso: Optional[Callable] = None,
             nome: str | None = None, **kwargs) -> Tarefa:
    """Roda funcao(*args, **kwargs) numa thread de trabalho. Com
    `ao_progresso`, a função recebe o argumento nomeado `ao_progresso`
    (o mesmo contrato do backend) e cada chamada chega aqui na interface."""
    executor, despachante = _iniciar()
    numero = next(_numeros)
    tarefa = Tarefa(numero, nome or getattr(funcao, "__name__", "tarefa"), ao_concluir, ao_falhar, ao_progresso)
    cancelada = tarefa._cancelada
    if ao_progresso is not None:
        def _avisar_progresso(*argumentos):
            if cancelada.is_set():
                raise TarefaCancelada()
            despachante.progresso.emit(numero, argumentos)
        kwargs["ao_progresso"] = _avisar_progresso
    _ativas[numero] = tarefa
    futuro = executor.submit(_rodar, numero, cancelada, despachante, funcao, args, kwargs)
    _futuros[numero] = futuro
    futuro.add_done_callback(lambda _f, n=numero: _futuros.pop(n, None))
    return tarefa


def ativas() -> int:
    """Quantas tarefas ainda não devolveram resultado à interface (útil nos testes)."""
    return len(_ativas)


def esperar_todas(ms: int = 60000) -> bool:
    """Espera as threads de trabalho terminarem (sem processar os callbacks)."""
    pendentes = list(_futuros.values())
    if not pendentes:
        return True
    _feitos, nao_feitos = wait(pendentes, timeout=ms / 1000)
    return not nao_feitos


def _coletar() -> None:
    """Coleta os ciclos de lixo, se nenhuma tarefa estiver rodando. Segue os
    limiares do próprio Python: só coleta a geração que já passou do limite."""
    if _futuros:
        return
    limites, contagem = gc.get_threshold(), gc.get_count()
    for geracao in (2, 1, 0):
        if contagem[geracao] > limites[geracao]:
            gc.collect(geracao)
            return


def instalar_coleta_de_lixo(app: QCoreApplication) -> None:
    """Desliga a coleta automática de lixo e passa a coletar na thread da
    interface, entre as tarefas (ver o topo do módulo). Chamar uma vez, com
    o QApplication criado."""
    if getattr(app, "_hidrolog_coletor", None) is not None:
        return
    gc.disable()
    timer = QTimer(app)
    timer.setInterval(INTERVALO_COLETA_MS)
    timer.timeout.connect(_coletar)
    timer.start()
    app._hidrolog_coletor = timer
