"""Camadas 2 e 3 da ingestao, do lado do nucleo: pede o PLANO ao plugin
(reconhecer), le as unidades (ler, em fluxo ou em paralelo) e GRAVA.

Gravar e igual para todos os sensores:
- deduplicacao pela chave natural declarada (Ingestao.chave), dentro do envio
  e contra o banco, lote a lote;
- insercao em lotes, na transacao do envio (o envio entra inteiro ou nada);
- progresso por unidade lida (paralelo.informar_progresso) e cancelamento
  (a funcao de progresso levanta uma excecao);
- uma unidade com problema vira um aviso e conta como ignorada; nunca
  derruba o envio (erros do envio em si, como limites e RAR sem programa,
  derrubam);
- ao_inserir(linhas) e chamado a cada lote de leituras novas (regras de qualidade).
"""

from __future__ import annotations

import importlib
import sys
from dataclasses import dataclass, field
from functools import partial
from typing import Callable, Iterable, Optional

from sqlalchemy import insert, select, tuple_
from sqlalchemy.orm import Session

from hidrolog_nucleo.plugin import ArquivoMemoria, PlanoImportacao, Plugin, Recusa, Unidade

from . import paralelo
from .erros import EnvioRecusado, ErroEnvio
from .tipos import ResumoImportacao

MAX_AVISOS_UNIDADE = 20


@dataclass
class _ErroUnidade:
    rotulo: str
    mensagem: str


def reconhecer(plugin: Plugin, arvore, verificar: bool = False) -> PlanoImportacao:
    """Plano do plugin para a arvore, ou EnvioRecusado com o motivo dele."""
    resultado = plugin.ingestao.reconhecer(arvore, verificar=verificar)
    if isinstance(resultado, Recusa):
        raise EnvioRecusado(resultado.motivo)
    if not isinstance(resultado, PlanoImportacao):
        raise TypeError(f"plugin {plugin.codigo}: reconhecer devolveu {type(resultado).__name__}, "
                        "esperado PlanoImportacao ou Recusa")
    return resultado


def _ler_lote(modulo: str, caminho_extra: Optional[str], unidades: list[Unidade]) -> list:
    """Roda nos processos do pool: le cada unidade com o plugin (importado
    pelo nome do modulo). Erro de uma unidade volta como _ErroUnidade."""
    if caminho_extra and caminho_extra not in sys.path:
        sys.path.insert(0, caminho_extra)
    plugin = importlib.import_module(modulo).PLUGIN
    saida: list = []
    for unidade in unidades:
        try:
            saida.append(list(plugin.ingestao.ler(unidade)))
        except ErroEnvio:
            raise
        except Exception as erro:  # noqa: BLE001
            saida.append(_ErroUnidade(unidade.rotulo, f"{type(erro).__name__}: {erro}"))
    return saida


def _em_memoria(unidade: Unidade) -> Unidade:
    """Copia da unidade com o conteudo lido (respeitando os limites do envio),
    para mandar a outro processo."""
    return Unidade(unidade.rotulo, [ArquivoMemoria(a.caminho, a.ler()) for a in unidade.arquivos],
                   dict(unidade.dados))


@dataclass
class _Gravador:
    sessao: Session
    plugin: Plugin
    equipamento_id: int
    envio_id: int
    ao_inserir: Optional[Callable[[list[dict]], None]] = None
    resumo: ResumoImportacao = field(default_factory=ResumoImportacao)
    series: set = field(default_factory=set)
    _vistos: set = field(default_factory=set)
    _lote: list = field(default_factory=list)

    def __post_init__(self):
        ing = self.plugin.ingestao
        self._tabela = ing.tabela
        self._chave = [c for c in ing.chave if c != "equipamento_id"]
        if not self._chave:
            raise ValueError(f"plugin {self.plugin.codigo}: a chave precisa de uma coluna alem do equipamento")

    def _chave_de(self, linha: dict):
        if len(self._chave) == 1:
            return linha.get(self._chave[0])
        return tuple(linha.get(c) for c in self._chave)

    def acrescentar(self, linha: dict) -> None:
        ing = self.plugin.ingestao
        r = self.resumo
        r.leituras += 1
        if ing.coluna_corrompido and linha.get(ing.coluna_corrompido):
            r.corrompidas += 1
        tempo = linha.get(ing.coluna_tempo)
        if tempo is not None:
            r.inicio = tempo if r.inicio is None or tempo < r.inicio else r.inicio
            r.fim = tempo if r.fim is None or tempo > r.fim else r.fim
        if ing.coluna_numero_serie:
            serie = linha.get(ing.coluna_numero_serie)
            if serie:
                self.series.add(str(serie).strip())
        self._lote.append(linha)
        if len(self._lote) >= ing.tamanho_lote:
            self.gravar_lote()

    def gravar_lote(self) -> None:
        if not self._lote:
            return
        lote, self._lote = self._lote, []
        chaves = [self._chave_de(l) for l in lote]
        candidatas = {k for k in chaves if k not in self._vistos}
        existentes: set = set()
        if candidatas:
            colunas = [getattr(self._tabela, c) for c in self._chave]
            filtro_eq = getattr(self._tabela, "equipamento_id") == self.equipamento_id
            valores = list(candidatas)
            for i in range(0, len(valores), 900):
                parte = valores[i:i + 900]
                if len(colunas) == 1:
                    consulta = select(colunas[0]).where(filtro_eq, colunas[0].in_(parte))
                    existentes.update(self.sessao.scalars(consulta))
                else:
                    consulta = select(*colunas).where(filtro_eq, tuple_(*colunas).in_(parte))
                    existentes.update(tuple(l) for l in self.sessao.execute(consulta))
        novas = []
        for linha, chave in zip(lote, chaves):
            if chave in self._vistos or chave in existentes:
                self.resumo.duplicadas += 1
                continue
            self._vistos.add(chave)
            novas.append(dict(linha, equipamento_id=self.equipamento_id, envio_id=self.envio_id))
        if novas:
            self.sessao.execute(insert(self._tabela), novas)
            self.resumo.novas += len(novas)
            if self.ao_inserir is not None:
                self.ao_inserir(novas)

    def erro_unidade(self, rotulo: str, mensagem: str) -> None:
        r = self.resumo
        r.ignorados += 1
        r.arquivos_ignorados.append(rotulo)
        n = sum(1 for a in r.avisos if a.startswith("nao foi possivel ler "))
        if n < MAX_AVISOS_UNIDADE:
            r.avisos.append(f"nao foi possivel ler {rotulo}: {mensagem}")


def importar(sessao: Session, envio, plugin: Plugin, plano: PlanoImportacao,
             caminho_extra: Optional[str] = None,
             ao_inserir: Optional[Callable[[list[dict]], None]] = None) -> ResumoImportacao:
    """Le as unidades do plano e grava as leituras do envio (sem commit)."""
    gravador = _Gravador(sessao, plugin, envio.equipamento_id, envio.id, ao_inserir)
    resumo = gravador.resumo
    for arquivo, motivo in _pares_ignorados(plano.ignorados):
        resumo.ignorados += 1
        resumo.arquivos_ignorados.append(arquivo)
    resumo.avisos.extend(plano.avisos)
    resumo.metadados = dict(plano.metadados)

    unidades = list(plano.unidades)
    total = len(unidades)
    avisar = paralelo.progresso_atual()
    if avisar is not None:
        avisar(0, total)

    if plugin.ingestao.leitura_paralela:
        # o pool decide: poucas unidades ou HIDROLOG_PROCESSOS=1 leem neste processo
        funcao = partial(_ler_lote, plugin.manifesto.modulo, caminho_extra)
        resultados = paralelo.mapear_lotes(funcao, [_em_memoria(u) for u in unidades])
        for unidade, linhas in zip(unidades, resultados):
            if isinstance(linhas, _ErroUnidade):
                gravador.erro_unidade(linhas.rotulo, linhas.mensagem)
                continue
            for linha in linhas:
                gravador.acrescentar(linha)
    else:
        passo = max(1, total // 50)
        for i, unidade in enumerate(unidades, 1):
            try:
                linhas: Iterable[dict] = plugin.ingestao.ler(unidade)
                for linha in linhas:
                    gravador.acrescentar(linha)
            except ErroEnvio:
                raise
            except Exception as erro:  # noqa: BLE001 - um problema numa unidade nao derruba o envio
                gravador.erro_unidade(unidade.rotulo, f"{type(erro).__name__}: {erro}")
            if avisar is not None and (i % passo == 0 or i == total):
                avisar(i, total)
    gravador.gravar_lote()

    serie_cadastro = (envio.equipamento.numero_serie or "").strip()
    series = set(gravador.series)
    meta = plano.metadados.get("numero_serie")
    if meta:
        series.update(str(s).strip() for s in ([meta] if isinstance(meta, str) else meta) if s)
    diferentes = sorted(s for s in series if serie_cadastro and s != serie_cadastro)
    if diferentes:
        resumo.avisos.append(
            f"numero de serie nos arquivos ({', '.join(diferentes)}) diferente do cadastrado "
            f"no equipamento ({serie_cadastro})")
    elif not serie_cadastro and len(series) == 1:
        # o nº de série não é digitado no cadastro: fica registrado o da primeira
        # importação que o trouxer, e os envios seguintes são conferidos contra ele
        envio.equipamento.numero_serie = next(iter(series))
        resumo.avisos.append(f"numero de serie {envio.equipamento.numero_serie} registrado no equipamento "
                             f"a partir das leituras")
    elif not serie_cadastro and len(series) > 1:
        resumo.avisos.append(f"arquivos com numeros de serie diferentes ({', '.join(sorted(series))}): "
                             f"nenhum foi registrado no equipamento")
    resumo.validas = resumo.leituras - resumo.corrompidas
    return resumo


def _pares_ignorados(ignorados) -> Iterable[tuple[str, str]]:
    for item in ignorados:
        if isinstance(item, (tuple, list)):
            arquivo, motivo = item[0], (item[1] if len(item) > 1 else "")
        else:
            arquivo, motivo = item, ""
        yield (getattr(arquivo, "caminho", None) or str(arquivo)), motivo
